/** @odoo-module **/
import { installDraftNavigation } from './draft_navigation';
import { calculationRows, isEmptyDraftLine, decorateLineGrid } from './line_grid';
import { createPurchaseUI } from './purchase_ui';
import { openAnalyticDistribution } from './analytic_editor';

export function mountSalesLines(root) {
    root.classList?.add('absar-purchase-controls');
    let state=JSON.parse(root.dataset.boot),revision=0,busy=false,dirty=false,timer,restoring=false,error='',pendingComputations=0,headerSequence=0;
    state.lines.forEach(line=>{line._manualPrice=Boolean(line.id);line._manualTaxes=Boolean(line.id);line._amountKey=amountKey(line);});
    const csrf=root.dataset.csrf;
    const defaultJobs=new Set();
    function trackDefaults(job){defaultJobs.add(job);job.then(()=>defaultJobs.delete(job),()=>defaultJobs.delete(job));return job;}
    function selectProduct(...args){return trackDefaults(selectProductDefaults(...args));}
    function reprice(...args){return trackDefaults(repriceDefaults(...args));}
    const surface=document.createElement('div');root.replaceChildren(surface);
    const money=v=>Number(v||0).toLocaleString(undefined,{minimumFractionDigits:2,maximumFractionDigits:2});
    async function post(path,payload={}){
        const headerRoot=document.getElementById('aps-new-details')||document.getElementById('aps-order-details');
        if(headerRoot)payload.header=Object.fromEntries(['partner_id','project_id','date_order','validity_date','kind','title'].filter(key=>headerRoot.querySelector('[name="'+key+'"]')).map(key=>[key,headerRoot.querySelector('[name="'+key+'"]')?.value||'']));
        const response=await fetch((state.order_id?'/my/employee/sales/'+state.order_id+'/line-api':'/my/employee/sales/new-api')+path,{method:'POST',credentials:'same-origin',body:new URLSearchParams({csrf_token:csrf,payload:JSON.stringify(payload)})});
        if(response.headers?.get && !(response.headers.get('content-type')||'').includes('application/json'))throw new Error('Your session or Sales permission changed. Reload this page.');
        const data=await response.json();if(!data.ok)throw new Error(data.error||'Unable to update quotation lines.');return data.result;
    }
    const ui=createPurchaseUI({root,post,companyId:state.company_id,readonly:!state.editable});
    const {text,button,lookup,modal}=ui;
    const control=(value,type,change)=>{const node=ui.input(value,type,v=>{change(v);changed();});node.disabled=!state.editable||busy;return node;};
    function amountKey(line){return JSON.stringify([line.quantity,line.price_unit,line.discount,line.taxes_id,line.uom_id]);}
    function lineAmount(line){return line && !line.display_type && Number.isFinite(Number(line.subtotal)) ? Number(line.subtotal) : null;}
    function blank(){const taxes=state.default_taxes||[];return {id:0,name:'',product_id:0,quantity:1,price_unit:0,discount:0,taxes_id:taxes.map(t=>t.id),taxes:taxes.map(t=>({...t})),_defaultTaxes:taxes.map(t=>t.id),analytic_distribution:{}};}
    function changed(){const review=document.querySelector('[data-aps-submit-review]');if(review)review.disabled=true;dirty=true;revision++;error='';state.lines.forEach(l=>{l._pending=true;});drawTotals();clearTimeout(timer);timer=setTimeout(preview,250);}
    function feedback(message){error=message;const node=root.querySelector('[data-sales-status]');if(node)node.textContent=message;drawTotals();}
    async function preview(){
        const seq=revision;
        if(!state.editable||busy||pendingComputations)return;
        const lines=calculationRows(state.lines);
        if(lines.some(l=>!l.display_type&&(!l.name||!l.uom_id||(!l.id&&!l.product_id)))){feedback('Choose a product and unit on each line to calculate totals.');return;}
        try{const amounts=await post('/preview',{lines});if(seq!==revision)return;
            Object.assign(state,{untaxed:amounts.untaxed,tax:amounts.tax,total:amounts.total});
            lines.forEach((line,i)=>{line.subtotal=amounts.line_amounts[i]??0;line._amountKey=amountKey(line);});state.lines.forEach(line=>{line._pending=false;});drawTotals();feedback('');
        }catch(e){if(seq===revision)feedback(e.message);}
    }
    function analyticName(line){return Object.entries(line.analytic_distribution||{}).map(([key,pct])=>key.split(',').map(id=>state.analytic_labels?.[id]?.label||id).join(' / ')+(Number(pct)===100?'':' ('+pct+'%)')).join(', ');}
    function analytic(line){
        const node=button(analyticName(line)||(!state.editable?'—':'Set distribution'),()=>openAnalyticDistribution({ui,distribution:line.analytic_distribution,labels:state.analytic_labels||{},readonly:!state.editable,onApply:(distribution,labels)=>{
            line.analytic_distribution=distribution;state.analytic_labels={...state.analytic_labels,...labels};changed();render();
        }}),'aps-sales-analytic');node.title=analyticName(line);return node;
    }
    function gridControl(row,col){return root.querySelector(`[data-sales-row="${row}"] [data-sales-column="${col}"] [data-sales-entry]`);}
    function moveGrid(row,col,dir=1){
        const entries=[...root.querySelectorAll('[data-sales-entry]')].filter(n=>!n.disabled),index=entries.indexOf(gridControl(row,col));if(index<0)return;
        let next=entries[index+dir];
        if(!next&&dir>0&&state.editable&&!busy&&state.lines[row]?.product_id&&state.lines.length<200){state.lines.push(blank());changed();render();next=gridControl(state.lines.length-1,0);}
        if(next){restoring=true;next.focus();restoring=false;next.select?.();next.scrollIntoView?.({block:'nearest',inline:'nearest'});}
    }
    async function selectProductDefaults(line,item){
        if(item?.product_updated&&line.product_id===item.id){for(const other of state.lines.filter(l=>l.product_id===item.id))other.product=item;changed();render();return;}
        const sequence=(line._selectionSequence||0)+1;line._selectionSequence=sequence;
        line.product_id=item?.id||0;line.product=item||null;line._manualPrice=false;line._manualTaxes=false;line.uom_id=0;line.uom=null;
        if(!item){changed();return;}
        const headerVersion=headerSequence;pendingComputations++;changed();
        try{const defaults=await post('/defaults',{product_id:item.id,quantity:line.quantity});
            if(line._selectionSequence!==sequence||headerVersion!==headerSequence||!state.lines.includes(line))return;
            const keep={id:line.id,analytic_distribution:line.analytic_distribution,_selectionSequence:sequence,
                ...(line._manualTaxes?{taxes_id:line.taxes_id,taxes:line.taxes}:{}),
                ...(line._manualPrice?{price_unit:line.price_unit,discount:line.discount,subtotal:line.subtotal,_manualPrice:true}:{_manualPrice:false})};
            Object.assign(line,defaults,keep);changed();render();
        }finally{pendingComputations--;if(!pendingComputations){clearTimeout(timer);timer=setTimeout(preview,250);}}
    }
    async function repriceDefaults(line,selectedUnit=null,force=false){
        if(!line.product_id)return;
        const sequence=(line._priceSequence||0)+1;line._priceSequence=sequence;
        const productId=line.product_id,headerVersion=headerSequence;pendingComputations++;
        try{const defaults=await post('/defaults',{product_id:productId,quantity:line.quantity,uom_id:selectedUnit?.id||line.uom_id});
            if(line._priceSequence!==sequence||headerVersion!==headerSequence||line.product_id!==productId||!state.lines.includes(line))return;
            line.uom_id=defaults.uom_id;line.uom=defaults.uom;
            if(!line.name)line.name=defaults.name;
            if(force||!line._manualPrice){line.price_unit=defaults.price_unit;line.discount=defaults.discount;}
            if(force||!line._manualTaxes){line.taxes_id=defaults.taxes_id;line.taxes=defaults.taxes;}changed();render();
        }catch(e){feedback(e.message);}
        finally{pendingComputations--;if(!pendingComputations){clearTimeout(timer);timer=setTimeout(preview,250);}}
    }
    async function selectUom(line,item){
        if(!item){line.uom_id=0;line.uom=null;changed();return;}
        await reprice(line,item); 
    }
    function addLine(type=''){
        if(busy||state.lines.length>=200)return;
        state.lines.push(type?{id:0,display_type:type,name:''}:blank());changed();render();gridControl(state.lines.length-1,0)?.focus();
    }
    function catalog(){
        const view=modal('Product Catalog'),search=ui.input('','search',()=>{offset=0;load(true);}),cards=text('div','','aps-sales-catalog'),message=text('p','');
        let offset=0,sequence=0;const more=button('Load More',()=>load(false));
        async function load(reset){const seq=++sequence;more.disabled=true;if(reset)cards.replaceChildren();
            try{const result=await post('/lookup',{kind:'product',q:search.value,offset});if(seq!==sequence)return;
                for(const item of result.items){const card=text('div','','aps-sales-catalog-item');const add=button('Add',async()=>{add.disabled=true;try{if(state.lines.length>=200)throw new Error('Use at most 200 lines.');const line=blank();state.lines.push(line);changed();await selectProduct(line,item);message.textContent='Added '+item.label;}catch(e){message.textContent=e.message;}finally{add.disabled=false;}},'btn btn-outline-primary');card.append(text('strong',item.label),add);cards.append(card);}
                offset+=result.items.length;more.hidden=!result.more;if(!offset)message.textContent='No matching products.';
            }catch(e){message.textContent=e.message;}finally{more.disabled=false;}}
        view.body.append(search,message,cards);view.foot.append(more);load(true);
    }
    async function productForm(id,name,onSaved){
        const defaults=await post(id?'/product-read':'/product-defaults',{id});
        const values={...defaults,name:defaults.name||name||'',categ_id:defaults.categ_id?.id||0,uom_id:defaults.uom_id?.id||0,income_account_id:defaults.income_account?.id||0};
        const view=modal(id?'Product: '+defaults.name:'Create Sales Product'),message=text('p','','text-danger');
        if(defaults.shared)view.body.append(text('p','General product details apply across companies. The income account is saved for this company.','apw-help'));
        for(const [label,key,type] of [['Product Name','name','text'],['Internal Reference','default_code','text'],['Sales Price','list_price','number'],['Sales Description','description_sale','text']])ui.field(label,ui.input(values[key],type,v=>{values[key]=v;}),view.body);
        const type=document.createElement('select');type.className='form-select';for(const [value,label] of [['consu','Goods'],['service','Service']]){const option=text('option',label);option.value=value;type.append(option);}type.value=values.type;type.addEventListener('change',()=>{values.type=type.value;});ui.field('Product Type',type,view.body);
        for(const [label,key,kind,selected] of [['Category','categ_id','category',defaults.categ_id],['Unit of Measure','uom_id','uom',defaults.uom_id],['Income Account','income_account_id','income-account',defaults.income_account]])ui.field(label,lookup(kind,selected,item=>{values[key]=item?.id||0;}),view.body);
        const taxes=new Map((defaults.taxes||[]).map(t=>[t.id,t])),host=text('div',''),chips=text('div','');
        function draw(){chips.replaceChildren();for(const tax of taxes.values()){const chip=text('span',tax.label,'apw-chip');chip.append(button('×',()=>{taxes.delete(tax.id);draw();},'apw-chip-remove'));chips.append(chip);}}
        host.append(lookup('tax',null,item=>{if(item){taxes.set(item.id,item);draw();}}),chips);draw();ui.field('Sales Taxes',host,view.body);view.body.append(message);
        const save=button(id?'Save Product':'Create and Add',async()=>{save.disabled=true;try{const item=await post(id?'/product-update':'/product-create',{...values,id,taxes_id:[...taxes.keys()]});view.dialog.close();await onSaved(item);}catch(e){message.textContent=e.message;save.disabled=false;}},'btn btn-primary');view.foot.append(save);
    }
    function tags(line,index){const box=text('div','','aps-sales-taxes');
        if(state.editable){const add=lookup('tax',null,item=>{if(item&&!line.taxes_id.includes(item.id)){line._manualTaxes=true;line.taxes_id.push(item.id);line.taxes.push(item);changed();render();}}, {},{advance:()=>moveGrid(index,5,1),onError:e=>feedback(e.message)});add.className+=' aps-tax-add';add.querySelector('input').placeholder='+';box.append(add);}
        for(const tax of line.taxes||[]){const chip=text('span',tax.label,'apw-chip');if(state.editable)chip.append(button('×',()=>{line._manualTaxes=true;line.taxes_id=line.taxes_id.filter(id=>id!==tax.id);line.taxes=line.taxes.filter(t=>t.id!==tax.id);changed();render();},'apw-chip-remove'));box.append(chip);}return box;
    }
    function drawTotals(){
        const pending=!error&&state.lines.some(l=>l._pending&&!isEmptyDraftLine(l)),empty=!calculationRows(state.lines).some(l=>!l.display_type);
        const totals=root.querySelector('[data-sales-totals]');if(totals){totals.replaceChildren();
            for(const [title,value] of [['Untaxed Amount',empty?0:state.untaxed],['Taxes',empty?0:state.tax],['Total',empty?0:state.total]]){
                const row=text('div','');row.append(text('span',title),text('strong',money(value)+' '+state.currency));totals.append(row);}
            totals.setAttribute('aria-busy',String(pending&&!empty));totals.append(text('small',pending&&!empty?'Updating…':'','apw-help'));}
        root.querySelectorAll('[data-sales-amount]').forEach(node=>{const line=state.lines[Number(node.dataset.salesAmount)];if(line)node.textContent=lineAmount(line)===null?'—':money(lineAmount(line));});
    }
    let draftJob=null,draftNavigate=true;
    function save(options={}){if(draftJob){if(options.navigate===false)draftNavigate=false;return draftJob;}draftNavigate=options.navigate!==false;const job=saveDraft(options);draftJob=job;job.then(()=>{draftJob=null;},()=>{draftJob=null;});return job;}
    async function saveDraft({navigate=true}={}){
        if(busy)return false;busy=true;clearTimeout(timer);render();feedback('Saving…');
        try{while(defaultJobs.size)await Promise.all([...defaultJobs]);state=await post(state.order_id?'/save':'/create',{version:state.version,lines:calculationRows(state.lines)});
            dirty=false;revision++;busy=false;
            state.lines.forEach(line=>{line._manualPrice=Boolean(line.id);line._manualTaxes=Boolean(line.id);line._amountKey=amountKey(line);});
            if(state.redirect){if(draftNavigate){window.location.assign(state.redirect);return true;}window.history?.replaceState(null,'',state.redirect);}
            render();feedback('Draft saved.');return true;
        }catch(e){busy=false;render();feedback(e.message);return false;}
    }
    function render(){
        const active=document.activeElement,cell=active?.closest?.('[data-sales-column]'),row=active?.closest?.('[data-sales-row]');
        const focus=cell&&row?[Number(row.dataset.salesRow),Number(cell.dataset.salesColumn),active.selectionStart,active.selectionEnd,active.classList?.contains('aps-sales-description')]:null;
        surface.querySelectorAll('.apw-lookup').forEach(node=>node.dispatchEvent(new Event('apw-dispose')));
        surface.replaceChildren();
        surface.append(text('div',error,'aps-sales-status'));surface.children[0].setAttribute('data-sales-status','true');surface.children[0].setAttribute('role','status');
        const wrap=text('div','','aps-sales-scroll'),table=text('table','','aps-sales-grid');
        const head=text('thead',''),hr=text('tr','');for(const title of ['Product','Analytic Distribution','Quantity','UoM','Unit Price','Taxes','Disc.%','Amount',''])hr.append(text('th',title));head.append(hr);table.append(head);
        const body=text('tbody','');
        if(!state.lines.length){const empty=text('tr',''),cell=text('td','Add a product, section or note.','apw-empty');cell.colSpan=9;empty.append(cell);body.append(empty);}
        state.lines.forEach((line,index)=>{
            const tr=text('tr','');tr.setAttribute('data-sales-row',index);let column=0;
            function td(node,entry=true){const cell=text('td','');cell.setAttribute('data-sales-column',column++);cell.append(node);
                const input=node.matches?.('input,button,select')?node:node.querySelector('input');if(entry&&input&&!input.disabled)input.setAttribute('data-sales-entry','true');tr.append(cell);return cell;}
            if(line.display_type){const cell=td(control(line.name,'text',v=>{line.name=v;}));cell.colSpan=8;tr.className=line.display_type;}
            else{
                const product=lookup('product',line.product||{label:line.name},item=>selectProduct(line,item),{}, {productForm:state.editable?productForm:undefined,advance:()=>moveGrid(index,0,1),onError:e=>feedback(e.message)});product.title=line.name;const productCell=text('div','');const description=document.createElement('textarea');description.className='form-control aps-sales-description';description.rows=1;description.value=line.name;description.disabled=!state.editable||busy;description.setAttribute('aria-label','Line description');description.addEventListener('input',()=>{line.name=description.value;changed();});productCell.append(product,description);td(productCell);
                td(analytic(line));const quantity=control(line.quantity,'number',v=>{line.quantity=Number(v);});quantity.addEventListener('change',()=>reprice(line));td(quantity);
                td(lookup('uom',line.uom,item=>selectUom(line,item),{},{advance:()=>moveGrid(index,3,1),onError:e=>feedback(e.message)}));
                td(control(line.price_unit,'number',v=>{line.price_unit=Number(v);line._manualPrice=true;}));td(tags(line,index));td(control(line.discount,'number',v=>{line.discount=Number(v);}));
                const amount=text('span','');amount.setAttribute('data-sales-amount',index);td(amount,false).className='num';
            }
            const tools=text('div','','aps-sales-tools');
            if(state.editable){const remove=button('×',()=>{state.lines.splice(index,1);render();changed();});remove.title='Remove line';remove.setAttribute('aria-label','Remove line');tools.append(remove);}td(tools,false);body.append(tr);
        });
        table.append(body);decorateLineGrid(table,{editor:'sales',editable:state.editable&&!busy,entrySelector:'[data-sales-entry]',onAppend:()=>{if(isEmptyDraftLine(state.lines.at(-1)))return false;moveGrid(state.lines.length-1,6,1);},onReorder:(from,to)=>{const [line]=state.lines.splice(from,1);if(line){state.lines.splice(to,0,line);render();changed();}}});table.addEventListener('keydown',event=>{
            if(event.key!=='Enter'||event.defaultPrevented||event.isComposing||event.target.closest('.apw-options')||!state.editable)return;if(event.ctrlKey&&event.target.tagName==='TEXTAREA')return;const input=event.target.closest('[data-sales-entry], .aps-sales-description');if(!input)return;
            event.preventDefault();moveGrid(Number(input.closest('[data-sales-row]').dataset.salesRow),Number(input.closest('[data-sales-column]').dataset.salesColumn),event.shiftKey?-1:1);
        });wrap.append(table);surface.append(wrap);
        if(state.editable){const actions=text('div','','aps-sales-line-actions absar-line-add');for(const [type,label] of [['','Add a product'],['line_section','Add a section'],['line_note','Add a note']]){
            const add=button(label,()=>{addLine(type);});add.disabled=busy;actions.append(add);}
            actions.append(button('Catalog',catalog));surface.append(actions);}
        document.querySelectorAll('[data-sales-save]').forEach(node=>{node.hidden=!state.editable;node.disabled=busy;node.textContent=busy?'Saving…':'Save Draft';});
        const totals=text('div','','aps-sales-totals');totals.setAttribute('data-sales-totals','true');surface.append(totals);drawTotals();
        const review=document.querySelector('[data-aps-submit-review]');if(review)review.disabled=dirty||!state.lines.some(l=>!l.display_type);
        if(!state.editable)root.querySelectorAll('input,select').forEach(node=>{node.disabled=true;});
        if(busy)root.querySelectorAll('input,button,select').forEach(node=>{node.disabled=true;});
        if(focus){const node=focus[4]?root.querySelector('[data-sales-row="'+focus[0]+'"] .aps-sales-description'):gridControl(focus[0],focus[1]);if(node){node.dataset.suppressLookupOnce='1';restoring=true;node.focus();restoring=false;if(typeof focus[2]==='number'&&(['text','search'].includes(node.type)||node.tagName==='TEXTAREA'))node.setSelectionRange?.(focus[2],focus[3]);}}
    }
    root.addEventListener('keydown',event=>{
        if(event.key!=='Enter'||!event.shiftKey||event.isComposing||!state.editable)return;
        if(event.ctrlKey&&event.target.tagName==='TEXTAREA')return;const input=event.target.closest('[data-sales-entry], .aps-sales-description');if(!input)return;
        event.preventDefault();event.stopPropagation();
        moveGrid(Number(input.closest('[data-sales-row]').dataset.salesRow),Number(input.closest('[data-sales-column]').dataset.salesColumn),-1);
    },true);
    const headerRoot=document.getElementById('aps-new-details')||document.getElementById('aps-order-details');
    headerRoot?.addEventListener('input',()=>{dirty=true;});
    headerRoot?.addEventListener('change',event=>{changed();if(['partner_id','date_order'].includes(event.target.name)){headerSequence++;for(const line of state.lines)if(!line.display_type)reprice(line,null,event.target.name==='partner_id');}});
    headerRoot?.addEventListener('submit',event=>{event.preventDefault();save();});
    document.querySelectorAll('[data-sales-save]').forEach(node=>node.addEventListener('click',save));
    installDraftNavigation({isDirty:()=>state.editable&&dirty,save:()=>save({navigate:false}),onError:e=>{if(!error)feedback(e.message);}});
    render();
    return {get state(){return state;},render,moveGrid,save,preview,selectProduct};
}
function start(){const root=document.getElementById('aps-line-editor');if(root&&!root.dataset.mounted){root.dataset.mounted='true';mountSalesLines(root);}}
if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',start);else start();
