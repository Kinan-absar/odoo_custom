/** @odoo-module **/
import { createPurchaseUI } from './purchase_ui';
import { openPurchaseProductDialog } from './purchase_product_form';
function startDirectory(){
    const root=document.getElementById('apw-products');if(!root||root.dataset.ready)return;root.dataset.ready='1';
    const trigger=root.querySelector('[data-product-new]');if(!trigger)return;
    const companyId=Number(root.dataset.companyId),csrf=root.querySelector('[name="csrf_token"]').value;
    const errorBox=root.querySelector('[role="alert"]');
    async function post(path,payload){
        const response=await fetch('/my/employee/purchase'+path,{method:'POST',credentials:'same-origin',headers:{'Content-Type':'application/x-www-form-urlencoded;charset=UTF-8'},body:new URLSearchParams({csrf_token:csrf,payload:JSON.stringify(payload)})});
        if(!(response.headers.get('content-type')||'').includes('application/json'))throw new Error('Your session changed. Reload this page.');
        const result=await response.json();if(!response.ok||result.error)throw new Error(result.error||'Unable to complete the request.');return result;
    }
    trigger.addEventListener('click',async()=>{
        trigger.disabled=true;errorBox.hidden=true;
        try{
            const ui=createPurchaseUI({root,post,companyId});
            await openPurchaseProductDialog({...ui,post,companyId,saveLabel:'Create Product',onCreate:async()=>window.location.reload()});
        }catch(error){errorBox.textContent=error.message;errorBox.hidden=false;}finally{trigger.disabled=false;}
    });
}
if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',startDirectory);else startDirectory();
