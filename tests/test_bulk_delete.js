const {test}=require('node:test');
const assert=require('node:assert/strict');
const vm=require('node:vm');
const fs=require('node:fs');
function fixture(confirmed){
 const rows=[{id:1,kind:'expense'},{id:2,kind:'transfer',transfer_id:'pair'}];
 const inputs=rows.map(r=>({dataset:{select:String(r.id)},checked:false}));
 const elements={};const $=id=>elements[id]??={value:'filter',querySelectorAll:()=>inputs};
 const calls=[],warnings=[];
 const c=vm.createContext({$,state:{},scopeRequest:0,allTransactions:[],selectedTransactions:new Set(),transactionRows:()=>rows,confirm:w=>{warnings.push(w);return confirmed;},api:async(path,method,data)=>{calls.push({path,method,data});return path==='/api/transactions'?{transactions:rows}:{deleted:3};},task:async fn=>fn(),renderTransactions:()=>{},syncMonthControl:()=>{},refresh:async()=>{},notify:()=>{}});
 const s=fs.readFileSync('static/app.js','utf8');
 vm.runInContext(s.slice(s.indexOf('function updateSelection()'),s.indexOf("$('#transaction-scope').onchange")),c);
 vm.runInContext(s.slice(s.indexOf("$('#select-all-transactions').onclick"),s.indexOf("$('#show-completed').onchange")),c);
 return {c,$,calls,warnings};
}
test('select all clears filters and includes transfers while disabling category assignment',async()=>{
 const {c,$}=fixture(false);
 await $('#select-all-transactions').onclick({currentTarget:{}});
 assert.equal($('#transaction-scope').value,'all');assert.equal($('#show-completed').checked,true);
 assert.equal($('#search').value,'');assert.equal($('#category-filter').value,'');
 assert.deepEqual([...c.selectedTransactions],[1,2]);assert.equal($('#apply-category').disabled,true);
 assert.equal($('#delete-selected').disabled,false);
});
test('cancel performs no deletion; confirm sends selected IDs and warns about linked transfers',async()=>{
 for(const confirmed of [false,true]){
  const {c,$,calls,warnings}=fixture(confirmed);c.selectedTransactions.add(2);
  await $('#delete-selected').onclick({currentTarget:{}});
  assert.match(warnings[0],/cannot be undone/);assert.match(warnings[0],/Both sides/);
  assert.equal(calls.length,confirmed?1:0);
  if(confirmed){assert.equal(calls[0].path,'/api/transactions/delete');assert.equal(calls[0].data.confirmed,true);assert.deepEqual([...calls[0].data.ids],[2]);}
 }
});
