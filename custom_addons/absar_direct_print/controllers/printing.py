import base64
import hashlib
import html
import json
import secrets
from datetime import timedelta
from odoo import fields, http
from odoo.http import request, content_disposition
from werkzeug.exceptions import Unauthorized, BadRequest

class DirectPrintController(http.Controller):
    def _wizard(self, wid):
        w = request.env['absar.print.wizard'].browse(wid).exists()
        if not w:
            raise BadRequest('Print request expired. Please print the report again.')
        w._report_args()
        return w
    @http.route('/absar-print/browser/<int:wid>', type='http', auth='user', methods=['GET'])
    def browser(self, wid):
        w=self._wizard(wid)
        report, ids, data = w._report_args()
        document = report._render_qweb_html(report.report_name, ids, data=data)[0].decode('utf-8')
        paper=report.paperformat_id or request.env.company.paperformat_id
        size = paper.format if paper and paper.format != 'custom' else 'A4'
        if paper and paper.format == 'custom':
            size = '%smm %smm' % (paper.page_width, paper.page_height)
        orientation = ' landscape' if paper and paper.orientation == 'Landscape' else ''
        margins = '%smm %smm %smm %smm' % (paper.margin_top,paper.margin_right,paper.margin_bottom,paper.margin_left) if paper else '10mm'
        toolbar = """<style>
        @page { size: %s%s; margin: %s; }
        .absar-print-toolbar{position:sticky;top:0;z-index:9999;background:#122a43;color:white;padding:12px 20px;display:flex;gap:12px;align-items:center;font:14px Arial}
        .absar-print-toolbar button,.absar-print-toolbar a{background:#087f8c;color:white;border:0;border-radius:6px;padding:8px 14px;text-decoration:none;cursor:pointer}
        @media print{.absar-print-toolbar{display:none!important}body{background:white!important}.article{box-shadow:none!important}}
        </style><div class="absar-print-toolbar"><strong>%s</strong><button onclick="window.print()">Print</button><a href="/absar-print/download/%s">Download PDF</a><span>Browser preview — check page breaks before printing.</span></div>
        <script>
        window.addEventListener('load', async function(){
          if(document.fonts) await document.fonts.ready;
          await Promise.all(Array.from(document.images).map(i=>i.complete?Promise.resolve():new Promise(r=>{i.onload=r;i.onerror=r;setTimeout(r,5000)})));
          setTimeout(()=>window.print(),300);
        });
        </script>""" % (size,orientation,margins,html.escape(w.name or 'Report'),wid)
        idx=document.lower().find('<body')
        if idx >= 0:
            pos=document.find('>',idx)+1
            document=document[:pos]+toolbar+document[pos:]
        else:
            document=toolbar+document
        return request.make_response(document,[('Content-Type','text/html; charset=utf-8'),('Cache-Control','no-store'),('X-Frame-Options','SAMEORIGIN')])
    @http.route('/absar-print/download/<int:wid>', type='http', auth='user', methods=['GET'])
    def download(self,wid):
        w=self._wizard(wid)
        report, ids, data=w._report_args()
        pdf=report._render_qweb_pdf(report.report_name,ids,data=data)[0]
        return request.make_response(pdf,[('Content-Type','application/pdf'),('Content-Disposition',content_disposition((w.name or 'Report')+'.pdf')),('Cache-Control','no-store')])
    def _station(self):
        auth = request.httprequest.headers.get('Authorization','')
        if not auth.startswith('Bearer ') or len(auth) > 200:
            raise Unauthorized()
        digest=hashlib.sha256(auth[7:].encode()).hexdigest()
        station=request.env['absar.print.station'].sudo().search([('token_hash','=',digest),('active','=',True)],limit=1)
        if not station:
            raise Unauthorized()
        return station
    def _json(self, data, status=200):
        return request.make_response(json.dumps(data),[('Content-Type','application/json'),('Cache-Control','no-store')],status=status)
    @http.route('/absar-print/agent/poll', type='http', auth='public', csrf=False, methods=['POST'], save_session=False)
    def poll(self):
        station=self._station()
        body=request.httprequest.get_json(silent=True) or {}
        station.write({'last_seen':fields.Datetime.now(), 'client_printers':str(body.get('printers',''))[:4000]})
        jobs=request.env['absar.print.job'].sudo()
        # A lost receipt must never automatically result in another physical print.
        jobs.search([('station_id','=',station.id),('state','=','claimed'),('claimed_at','<',fields.Datetime.now()-timedelta(minutes=10))]).write({'state':'uncertain','message':'Station did not confirm submission. Check the printer before retrying.'})
        request.env.cr.execute("SELECT id FROM absar_print_job WHERE station_id=%s AND state='queued' ORDER BY id FOR UPDATE SKIP LOCKED LIMIT 1",[station.id])
        row=request.env.cr.fetchone()
        if not row:
            return self._json({'job':None})
        job=jobs.browse(row[0])
        if not job.pdf_data:
            job.write({'state':'failed','message':'Document expired. Generate a new print job.'})
            return self._json({'job':None})
        claim=secrets.token_urlsafe(32)
        job.write({'state':'claimed','claimed_at':fields.Datetime.now(),'claim_id':claim})
        return self._json({'job':{'id':job.id,'claim':claim,'name':job.name,'copies':job.copies,
            'printer':job.printer_name or '', 'pdf':job.pdf_data.decode() if isinstance(job.pdf_data,bytes) else job.pdf_data}})
    @http.route('/absar-print/agent/ack', type='http', auth='public', csrf=False, methods=['POST'], save_session=False)
    def ack(self):
        station=self._station()
        b=request.httprequest.get_json(silent=True) or {}
        if type(b.get('id')) is not int or b.get('state') not in ('submitted','failed','uncertain'):
            raise BadRequest('Invalid receipt')
        request.env.cr.execute('SELECT id FROM absar_print_job WHERE id=%s AND station_id=%s FOR UPDATE',[b['id'],station.id])
        if not request.env.cr.fetchone():
            raise Unauthorized()
        job=request.env['absar.print.job'].sudo().browse(b['id'])
        if not secrets.compare_digest(job.claim_id or '',str(b.get('claim',''))):
            raise Unauthorized()
        if job.state in ('claimed','uncertain'):
            vals={'state':b['state'],'finished_at':fields.Datetime.now(),'message':str(b.get('message',''))[:2000]}
            if b['state']=='submitted':
                vals['pdf_data']=False
            job.write(vals)
        return self._json({'ok':True})
