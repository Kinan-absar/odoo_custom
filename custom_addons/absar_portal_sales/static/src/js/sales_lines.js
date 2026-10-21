/** @odoo-module **/
import { createPurchaseUI } from './purchase_ui';
import { openAnalyticDistribution } from './analytic_editor';

export function mountSalesLines(root) {
    root.classList?.add('absar-purchase-controls');
    let state=JSON.parse(root.dataset.boot),revision=0,busy=false,dirty=false,timer,restoring=false,error='';
    const csrf=root.dataset.csrf;
    const money=v=>Number(v||0).toLocaleString(undefined,{minimumFractionDigits:2,maximumFractionDigits:2});
    async function post(path,payload={}){
        const headerRoot=document.getElementById('aps-new-details');
        if(headerRoot)payload.header=Object.fromEntries(['partner_id','project_id','validity_date','kind'].map(key=>[key,headerRoot.querySelector('[name="'+key+'"]')?.value||'']));
        const response=await fetch((state.order_id?'/my/employee/sales/'+state.order_id+'/line-api':'/my/employee/sales/new-api')+path,{method:'POST',credentials:'same-origin',body:new URLSearchParams({csrf_token:csrf,payload:JSON.stringify(payload)})});
        const data=await response.json();if(!data.ok)throw new Error(data.error||'Unable to update quotation lines.');return data.result;
    }
    const ui=createPurchaseUI({root,post,companyId:state.company_id,readonly:!state.editable});
    const {text,button,lookup,modal}=ui;
    const control=(value,type,change)=>{const node=ui.input(value,type,v=>{change(v);changed();});node.disabled=!state.editable||busy;return node;};
    function blank(){return {id:0,name:'',product_id:0,quantity:1,price_unit:0,discount:0,taxes_id:[],taxes:[],analytic_distribution:{}};}
    function changed(){const review=document.querySelector('[data-aps-submit-review]');if(review)review.disabled=true;dirty=true;revision++;error='';state.lines.forEach(l=>{l._pending=true;});drawTotals();clearTimeout(timer);timer=setTimeout(preview,400);}
    function feedback(message){error=message;const node=root.querySelector('[data-sales-status]');if(node)node.textContent=message;drawTotals();}
    async function preview(){
        const seq=revision;
        if(!state.editable||busy)return;
        if(state.lines.some(l=>!l.display_type&&(!l.name||!l.uom_id||(!l.id&&!l.product_id)))){feedback('Choose a product and unit on each line to calculate totals.');return;}
        try{const amounts=await post('/preview',{lines:state.lines});if(seq!==revision)return;
            Object.assign(state,{untaxed:amounts.untaxed,tax:amounts.tax,total:amounts.total});
            state.lines.forEach((line,i)=>{line.subtotal=amounts.line_amounts[i]||0;line._pending=false;});drawTotals();feedback('');
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
        if(!next&&dir>0&&state.editable&&!busy&&state.lines.length<200){state.lines.push(blank());changed();render();next=gridControl(state.lines.length-1,0);}
        if(next){restoring=true;next.focus();restoring=false;next.select?.();next.scrollIntoView?.({block:'nearest',inline:'nearest'});}
    }
    async function selectProduct(line,item){
        if(item?.product_updated&&line.product_id===item.id){for(const other of state.lines.filter(l=>l.product_id===item.id))other.product=item;changed();render();return;}
        const current=(line._selectionSequence||0)+1;line._selectionSequence=current;
        if(!item){line.product_id=0;line.product=null;changed();return;}
        const defaults=await post('/defaults',{product_id:item.id,quantity:line.quantity});
        if(line._selectionSequence!==current||!state.lines.includes(line))return;
        const keep={id:line.id,analytic_distribution:line.analytic_distribution};Object.assign(line,defaults,keep);changed();render();
    }
    async function selectUom(line,item){
        const sequence=(line._uomSequence||0)+1;line._uomSequence=sequence;
        if(!item){line.uom_id=0;line.uom=null;changed();return;}
        const productId=line.product_id;
        const defaults=productId?await post('/defaults',{product_id:productId,quantity:line.quantity,uom_id:item.id}):null;
        if(line._uomSequence!==sequence||line.product_id!==productId||!state.lines.includes(line))return;
        line.uom_id=item.id;line.uom=item;if(defaults)line.price_unit=defaults.price_unit;
        changed();render();
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
    function details(line){const view=modal('Product / Line Details');
        const desc=control(line.name,'text',v=>{line.name=v;});ui.field('Description',desc,view.body);
        if(line.product?.label)view.body.append(text('p',line.product.label,'apw-help'));
        view.foot.append(button('Done',()=>{view.dialog.close();render();}));
    }
    function tags(line,index){const box=text('div','','aps-sales-taxes');
        if(state.editable){const add=lookup('tax',null,item=>{if(item&&!line.taxes_id.includes(item.id)){line.taxes_id.push(item.id);line.taxes.push(item);changed();render();}}, {},{advance:()=>moveGrid(index,5,1),onError:e=>feedback(e.message)});add.className+=' aps-tax-add';add.querySelector('input').placeholder='+';box.append(add);}
        for(const tax of line.taxes||[]){const chip=text('span',tax.label,'apw-chip');if(state.editable)chip.append(button('×',()=>{line.taxes_id=line.taxes_id.filter(id=>id!==tax.id);line.taxes=line.taxes.filter(t=>t.id!==tax.id);changed();render();},'apw-chip-remove'));box.append(chip);}return box;
    }
    function drawTotals(){
        const totals=root.querySelector('[data-sales-totals]');if(totals){totals.replaceChildren();for(const [title,value] of [['Untaxed Amount',state.untaxed],['Taxes',state.tax],['Total',state.total]]){
            const row=text('div','');row.append(text('span',title),text('strong',(state.lines.some(l=>l._pending)?(error?'—':'Recalculating…'):money(value))+' '+state.currency));totals.append(row);}}
        root.querySelectorAll('[data-sales-amount]').forEach(node=>{const line=state.lines[Number(node.dataset.salesAmount)];node.textContent=line._pending?'—':money(line.subtotal);});
    }
    async function save(){
        if(busy)return;busy=true;clearTimeout(timer);render();feedback('Saving…');
        try{state=await post(state.order_id?'/save':'/create',{version:state.version,lines:state.lines});if(state.redirect){window.location.assign(state.redirect);return;}dirty=false;revision++;busy=false;render();feedback('Lines saved.');}
        catch(e){busy=false;render();feedback(e.message);}
    }
    function render(){
        const active=document.activeElement,cell=active?.closest?.('[data-sales-column]'),row=active?.closest?.('[data-sales-row]');
        const focus=cell&&row?[Number(row.dataset.salesRow),Number(cell.dataset.salesColumn),active.selectionStart,active.selectionEnd]:null;
        root.querySelectorAll('.apw-lookup').forEach(node=>node.dispatchEvent(new Event('apw-dispose')));
        root.replaceChildren();
        root.append(text('div',error,'aps-sales-status'));root.children[0].setAttribute('data-sales-status','true');root.children[0].setAttribute('role','status');
        const wrap=text('div','','aps-sales-scroll'),table=text('table','','aps-sales-grid');
        const head=text('thead',''),hr=text('tr','');for(const title of ['Product','Analytic Distribution','Quantity','UoM','Unit Price','Taxes','Disc.%','Amount',''])hr.append(text('th',title));head.append(hr);table.append(head);
        const body=text('tbody','');
        state.lines.forEach((line,index)=>{
            const tr=text('tr','');tr.setAttribute('data-sales-row',index);let column=0;
            function td(node,entry=true){const cell=text('td','');cell.setAttribute('data-sales-column',column++);cell.append(node);
                const input=node.matches?.('input,button,select')?node:node.querySelector('input');if(entry&&input&&!input.disabled)input.setAttribute('data-sales-entry','true');tr.append(cell);return cell;}
            if(line.display_type){const cell=td(control(line.name,'text',v=>{line.name=v;}));cell.colSpan=8;tr.className=line.display_type;}
            else{
                const product=lookup('product',line.product||{label:line.name},item=>selectProduct(line,item),{}, {productForm:state.editable?productForm:undefined,advance:()=>moveGrid(index,0,1),onError:e=>feedback(e.message)});product.title=line.name;td(product);
                td(analytic(line));td(control(line.quantity,'number',v=>{line.quantity=Number(v);}));
                td(lookup('uom',line.uom,item=>selectUom(line,item),{},{advance:()=>moveGrid(index,3,1),onError:e=>feedback(e.message)}));
                td(control(line.price_unit,'number',v=>{line.price_unit=Number(v);}));td(tags(line,index));td(control(line.discount,'number',v=>{line.discount=Number(v);}));
                const amount=text('span','');amount.setAttribute('data-sales-amount',index);td(amount,false).className='num';
            }
            const tools=text('div','','aps-sales-tools');tools.append(button('⋯',()=>details(line)));
            if(state.editable)tools.append(button('×',()=>{state.lines.splice(index,1);changed();render();}));td(tools,false);body.append(tr);
        });
        table.append(body);table.addEventListener('keydown',event=>{
            if(event.key!=='Enter'||event.defaultPrevented||event.isComposing||event.target.closest('.apw-options')||!state.editable)return;const input=event.target.closest('[data-sales-entry]');if(!input)return;
            event.preventDefault();moveGrid(Number(input.closest('[data-sales-row]').dataset.salesRow),Number(input.closest('[data-sales-column]').dataset.salesColumn),event.shiftKey?-1:1);
        });wrap.append(table);root.append(wrap);
        if(state.editable){const actions=text('div','','aps-sales-line-actions');for(const [type,label] of [['','Add a product'],['line_section','Add a section'],['line_note','Add a note']]){
            const add=button(label,()=>{state.lines.push(type?{id:0,display_type:type,name:''}:blank());changed();render();gridControl(state.lines.length-1,0)?.focus();});add.disabled=busy;actions.append(add);}
            const saveButton=button(state.order_id?'Save Lines':'Save Quotation',save,'btn btn-primary');saveButton.disabled=busy;actions.append(saveButton);root.append(actions);}
        const totals=text('div','','aps-sales-totals');totals.setAttribute('data-sales-totals','true');root.append(totals);drawTotals();
        const review=document.querySelector('[data-aps-submit-review]');if(review)review.disabled=dirty||!state.lines.some(l=>!l.display_type);
        if(!state.editable)root.querySelectorAll('input,select').forEach(node=>{node.disabled=true;});
        if(busy)root.querySelectorAll('input,button,select').forEach(node=>{node.disabled=true;});
        if(focus){const node=gridControl(focus[0],focus[1]);if(node){node.dataset.suppressLookupOnce='1';restoring=true;node.focus();restoring=false;if(typeof focus[2]==='number'&&['text','search'].includes(node.type))node.setSelectionRange?.(focus[2],focus[3]);}}
    }
    root.addEventListener('keydown',event=>{
        if(event.key!=='Enter'||!event.shiftKey||event.isComposing||!state.editable)return;
        const input=event.target.closest('[data-sales-entry]');if(!input)return;
        event.preventDefault();event.stopPropagation();
        moveGrid(Number(input.closest('[data-sales-row]').dataset.salesRow),Number(input.closest('[data-sales-column]').dataset.salesColumn),-1);
    },true);
    const headerRoot=document.getElementById('aps-new-details');
    headerRoot?.addEventListener('change',()=>{changed();if(state.lines.length)feedback('Customer or details changed. Check line prices and taxes before saving.');});
    render();
    return {get state(){return state;},render,moveGrid,save,preview,selectProduct};
}
function start(){const root=document.getElementById('aps-line-editor');if(root&&!root.dataset.mounted){root.dataset.mounted='true';mountSalesLines(root);}}
if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',start);else start();
