import base64
import hashlib
import json
import secrets
from datetime import timedelta
from odoo import fields, http
from odoo.http import request
from werkzeug.exceptions import Unauthorized, BadRequest

class DirectPrintController(http.Controller):
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
