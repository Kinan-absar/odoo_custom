/** @odoo-module **/
// Purchase allocation editor, shared unchanged by the Sales/Accounting adapters.
export function openAnalyticDistribution({ui,distribution={},labels={},readonly=false,onApply=()=>{}}) {
    const {modal,text,button,input,lookup}=ui;
    const view=modal('Analytic Distribution');
    view.body.append(text('p','Allocate each plan to 100%. A row can combine one account from each plan.','apw-help'));
    const rows=Object.entries(distribution).map(([key,pct])=>({accounts:key.split(',').map(id=>labels[id]||{id:Number(id),label:id}),pct}));
    if(!rows.length)rows.push({accounts:[],pct:100});
    const table=text('div','');view.body.append(table);
    const message=text('p','','text-danger');view.body.append(message);
    function draw(){
        table.replaceChildren();
        rows.forEach((r,i)=>{
            const row=text('div','','apw-allocation'),accounts=text('div','');
            for(const a of r.accounts){
                const chip=text('span',a.label+(a.plan?' · '+a.plan:''),'apw-chip');
                if(!readonly)chip.append(button('×',()=>{r.accounts=r.accounts.filter(x=>x.id!==a.id);draw();},'apw-chip-remove'));
                accounts.append(chip);
            }
            if(!readonly)accounts.append(lookup('analytic',null,item=>{
                if(!item)return;
                if(r.accounts.some(a=>a.id===item.id||((a.plan_id||a.plan)&&(a.plan_id||a.plan)===(item.plan_id||item.plan)))){message.textContent='Use one account per plan in each row.';return;}
                r.accounts.push(item);message.textContent='';draw();
            }));
            const percent=input(r.pct,'number',v=>{r.pct=Number(v);});percent.min='0';percent.max='100';percent.disabled=readonly;percent.setAttribute('aria-label','Allocation percentage');
            row.append(accounts,percent,text('span','%'));
            if(!readonly)row.append(button('Remove',()=>{rows.splice(i,1);draw();}));
            table.append(row);
        });
    }
    draw();
    if(!readonly){
        view.foot.append(button('Add a Line',()=>{rows.push({accounts:[],pct:100});draw();}));
        view.foot.append(button('Apply',()=>{
            const distribution={},accountLabels={},sums={};
            for(const row of rows){
                if(!row.accounts.length&&!row.pct)continue;
                if(!row.accounts.length||!Number.isFinite(row.pct)||row.pct<=0||row.pct>100){message.textContent='Every row needs an account and a percentage greater than zero, up to 100.';return;}
                const key=row.accounts.map(a=>a.id).sort((a,b)=>a-b).join(',');
                if(key in distribution){message.textContent='Combine duplicate account rows.';return;}
                distribution[key]=row.pct;
                for(const a of row.accounts){accountLabels[a.id]=a;const plan=a.plan_id||a.plan||a.id;sums[plan]=(sums[plan]||0)+row.pct;}
            }
            if(Object.values(sums).some(n=>Math.abs(n-100)>.01)){message.textContent='Each used plan must total 100%.';return;}
            onApply(distribution,accountLabels);view.dialog.close();
        },'btn btn-primary'));
        view.foot.append(button('Clear distribution',()=>{onApply({},{});view.dialog.close();}));
    }
    return view;
}
