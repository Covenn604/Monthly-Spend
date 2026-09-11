'use strict';
const $ = s => document.querySelector(s);
const esc = v => String(v ?? '').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
let recoveryToken='',resetToken='';
let state, report, csvText='', csvHeaders=[], importPreview=null, view='overview', noticeTimer;
let allTransactions=[], selectedTransactions=new Set(), scopeRequest=0, headerRequest=0, previewRequest=0, importProfileAccount=null;
function transactionRows(){return $('#transaction-scope').value==='all'?allTransactions:(report?.transactions||[]);}
function syncMonthControl(){$('#month').disabled=view==='transactions'&&$('#transaction-scope').value==='all';}
const localDay=()=>{const d=new Date();return `${d.getFullYear()}-${String(d.getMonth()+1).padStart(2,'0')}-${String(d.getDate()).padStart(2,'0')}`;};
$('#month').value=localDay().slice(0,7);
function clearPrivateState(){
 recoveryToken='';resetToken='';$('#setup-form').reset();$('#account-setup').hidden=true;$('#recovery').hidden=true;
 importProfileAccount=null;++previewRequest;
 state=null;report=null;allTransactions=[];csvText='';csvHeaders=[];importPreview=null;selectedTransactions.clear();scopeRequest++;headerRequest++;
 for(const id of ['tx-body','review-body','import-result','account-list','category-chips','rules-list','users-list','category-list','insights','trend','overview-balances','profile-identity'])$('#'+id).replaceChildren();
 for(const id of ['tx-form','account-form','category-form','rule-form','password-form','user-form','manage-user-form','category-edit-form','category-delete-form','account-edit-form'])$('#'+id).reset();
 $('#csv-file').value='';$('#skip-lines').value='0';$('#profile-name').value='';$('#mapping').hidden=true;$('#review').hidden=true;$('#user-admin').hidden=true;
 $('#transaction-scope').value='month';$('#show-completed').checked=false;$('#search').value='';$('#category-filter').value='';
 $('#tx-dialog').close();$('#category-dialog').close();$('#account-edit-dialog').close();if($('#user-action').onchange)$('#user-action').onchange();setView('overview');
}
function notify(message){$('#notice').textContent=message;$('#notice').classList.add('show');clearTimeout(noticeTimer);noticeTimer=setTimeout(()=>$('#notice').classList.remove('show'),7000);}
async function api(path,method='GET',data){const response=await fetch(path,{method,headers:{'Content-Type':'application/json','X-Requested-With':'MonthlySpend'},body:data===undefined?undefined:JSON.stringify(data)});const result=await response.json();if(!response.ok){if(response.status===401){clearPrivateState();$('#shell').hidden=true;$('#login').hidden=false;}throw Error(result.error||'Request failed.');}return result;}
function money(cents){return new Intl.NumberFormat('en-CA',{style:'currency',currency:state?.currency||'CAD',currencySign:'accounting'}).format(cents/100);}
function moneyHtml(cents){return `<span class="${cents<0?'money-negative':'money-value'}">${esc(money(cents))}</span>`;}

function opts(items,value='',blank='Choose…'){return `<option value="">${esc(blank)}</option>`+items.map(x=>`<option value="${esc(x.id)}" ${String(x.id)===String(value)?'selected':''}>${esc(x.name)}</option>`).join('');}
function setView(name){view=name;document.querySelectorAll('.view').forEach(el=>el.hidden=el.id!==name);document.querySelectorAll('nav button').forEach(b=>{b.classList.toggle('active',b.dataset.view===name);if(b.dataset.view===name)b.setAttribute('aria-current','page');else b.removeAttribute('aria-current');});$('#page-title').textContent={overview:'Monthly overview',transactions:'Transactions',import:'Import transactions',accounts:'Accounts & categories',settings:'Profile & users'}[name];syncMonthControl();}
async function refresh(){const session=await api('/api/auth-state');if(session.user.setup_required){showSetup(session.questions);return;}$('#account-setup').hidden=true;state=await api('/api/state');report=await api('/api/month?month='+encodeURIComponent($('#month').value));if($('#transaction-scope').value==='all')allTransactions=(await api('/api/transactions')).transactions;$('#login').hidden=true;$('#shell').hidden=false;renderState();renderOverview();renderTransactions();await renderUsers();if(importProfileAccount!==$('#import-account').value)await selectAccountProfile();else updateProfileControls();}
function renderState(){
 $('#currency-note').textContent=`${state.user.username} · ${state.currency}`;
 for(const id of ['tx-account','tx-destination','import-account']){const el=$('#'+id),old=el.value;el.innerHTML=opts(state.accounts,old);if(!el.value&&state.accounts.length)el.value=state.accounts[0].id;}
 const bulk=$('#bulk-category'),oldBulk=bulk.value;bulk.innerHTML=opts(state.categories,oldBulk,'Choose category…')+'<option value="none">Uncategorized</option>';bulk.value=oldBulk;
 $('#tx-category').innerHTML=opts(state.categories,'','Uncategorized / merchant rule');$('#rule-category').innerHTML=opts(state.categories);
 const filter=$('#category-filter'),old=filter.value;filter.innerHTML='<option value="">All categories</option><option value="none">Uncategorized</option>'+state.categories.map(c=>`<option value="${c.id}">${esc(c.name)}</option>`).join('');filter.value=old;
 const profile=$('#profile'),p=profile.value;profile.innerHTML='<option value="">New mapping</option>'+state.profiles.map(x=>`<option value="${esc(x.name)}">${esc(x.name)}</option>`).join('');profile.value=p;
 $('#account-list').innerHTML=state.accounts.length?state.accounts.map(a=>`<div class="account-row"><span>${esc(a.name)}<small>Balance including all entered transactions</small></span><div class="account-actions"><strong>${moneyHtml(a.balance)}</strong><button class="secondary" data-edit-opening="${a.id}" aria-label="Edit opening balance for ${esc(a.name)}">Edit opening balance</button></div></div>`).join(''):'<p class="empty">Add your first account to start tracking.</p>';
 $('#category-chips').innerHTML=state.categories.map(c=>`<button class="chip secondary" data-edit-category="${c.id}" aria-label="Edit ${esc(c.name)}">${esc(c.name)} · Edit</button>`).join('');
 $('#rules-list').innerHTML=state.rules.map(r=>`<div class="rule-row"><span><strong>${esc(r.contains_text)}</strong> → ${esc(r.category)}</span><button class="secondary" data-delete-rule="${r.id}">Remove</button></div>`).join('');
}
function renderAccountBalances(){
 $('#overview-balances').innerHTML=state.accounts.length?state.accounts.map(a=>`<article class="balance-card"><h3>${esc(a.name)}</h3><strong class="balance-value ${a.balance<0?'up':''}">${moneyHtml(a.balance)}</strong><dl><div><dt>Recorded activity</dt><dd>${moneyHtml(a.balance-a.opening)}</dd></div></dl></article>`).join(''):'<p class="empty">No accounts yet. Add an account in Accounts & categories to see its balance here.</p>';
}
function renderOverview(){
 renderAccountBalances();
 $('#income').innerHTML=moneyHtml(report.income);$('#expenses').innerHTML=moneyHtml(report.expenses);$('#remaining').innerHTML=moneyHtml(report.remaining);$('#remaining-label').textContent=report.remaining>=0?'Left over':'Over income';$('.emphasis').classList.toggle('deficit',report.remaining<0);$('#remaining-note').textContent=report.remaining>=0?'Income minus expenses · before upcoming bills':'Expenses exceed recorded income';
 $('#overview-note').textContent=report.partial?`Future-dated entries are excluded from the monthly income and expense figures. Transfers are excluded from income and expenses.`:'Recorded transactions for this month. Transfers are excluded from income and expenses.';
 const max=Math.max(...report.categories.map(c=>c.spent),1);
 $('#category-list').innerHTML=report.categories.length?report.categories.map(c=>`<button class="category-row" data-category="${c.id??'none'}"><div class="category-top"><span>${esc(c.name)}</span><span>${moneyHtml(c.spent)}</span></div><div class="track"><div class="fill" style="width:${Math.max(0,c.spent)/max*100}%"></div></div><div class="category-bottom"><span>${report.expenses>0&&c.spent>=0?Math.round(c.spent/report.expenses*100)+'% of net expenses':'Net expenses after refunds'}</span><span class="${c.difference>0?'up':c.difference<0?'down':''}">${c.average===null?'No comparison yet':moneyHtml(Math.abs(c.difference))+(c.difference>0?' above usual':c.difference<0?' below usual':' change')}</span></div></button>`).join(''):'<div class="empty">No expenses recorded for this month. Add a transaction or import a statement to see where your money goes.</div>';
 $('#comparison-note').textContent=report.periods.length?`Compared with ${report.periods.length} prior calendar month(s).`:'Import earlier months to establish your usual spending. Above usual means an increase, not necessarily unaffordable spending.';
 const increases=report.categories.filter(c=>c.difference>0).sort((a,b)=>b.difference-a.difference).slice(0,3);
 $('#insights').innerHTML=increases.length?increases.map(c=>`<div class="insight"><h3>${esc(c.name)}</h3><strong class="up">${moneyHtml(c.difference)} more</strong><p>${moneyHtml(c.spent)} this month · ${moneyHtml(c.average)} usual</p></div>`).join(''):`<p class="empty">${report.periods.length?'No categories are above their recorded average.':'Your spending patterns will appear here as you add history.'}</p>`;
 const peak=Math.max(...report.trend.flatMap(t=>[t.income,t.expenses]),1);
 $('#trend').innerHTML=report.trend.map(t=>`<div class="trend-col"><div class="bars" role="img" aria-label="${esc(t.month)}: income ${esc(money(t.income))}, expenses ${esc(money(t.expenses))}"><div class="bar income" style="height:${Math.max(0,t.income)/peak*100}%"></div><div class="bar" style="height:${Math.max(0,t.expenses)/peak*100}%"></div></div><small>${new Date(t.month+'-15T12:00:00').toLocaleDateString('en-CA',{month:'short'})}</small><div class="trend-values">${t.has_data?moneyHtml(t.income)+'<br>'+moneyHtml(t.expenses):'No records'}</div></div>`).join('');
}
function renderTransactions(){selectedTransactions.clear();const cleanup=$('#transaction-scope').value==='all'&&!$('#show-completed').checked;$('#show-completed-label').hidden=$('#transaction-scope').value!=='all';$('#category-filter').disabled=cleanup;if(cleanup)$('#category-filter').value='none';const search=$('#search').value.trim().toLowerCase(),filter=$('#category-filter').value;const rows=transactionRows().filter(t=>(!cleanup||(['expense','refund'].includes(t.kind)&&!t.category_id))&&(!search||[t.payee,t.account,t.note].join(' ').toLowerCase().includes(search))&&(!filter||(filter==='none'?!t.category_id:String(t.category_id)===filter)));$('#tx-count').textContent=`${rows.length} ${cleanup?'to categorize':'transactions'} · ${$('#transaction-scope').value==='all'?'All dates':$('#month').value}`;
 $('#tx-body').innerHTML=rows.length?rows.map(t=>`<tr><td><input type="checkbox" data-select="${t.id}" aria-label="Select ${esc(t.payee)} on ${esc(t.date)}" ${['expense','refund'].includes(t.kind)?'':'disabled title="Only expenses and refunds use spending categories"'}></td><td>${esc(t.date)}</td><td><strong>${esc(t.payee)}</strong><small>${esc(t.account)}</small></td><td>${t.kind==='income'||t.kind==='transfer'?'—':esc(t.category)}<small>${esc(t.kind)}${t.transfer_id?' · linked':''}</small></td><td class="transaction-notes">${esc(t.note||'')}</td><td class="number ${t.amount>0?'down':''}">${moneyHtml(t.amount)}</td><td>${!t.transfer_id?`<button class="secondary" data-edit="${t.id}">Edit</button> `:''}<button class="secondary" data-delete="${t.id}">Delete</button></td></tr>`).join(''):`<tr><td colspan="7" class="empty">${cleanup?(search?'No uncategorized expenses or refunds match your search.':'All caught up — no expenses or refunds need a category. Show categorized, income and transfers to review other records.'):'No matching transactions in this date range.'}</td></tr>`;
 updateSelection();
}
function txType(){const editing=!!$('#tx-form').elements.id.value,transfer=$('#tx-kind').value==='transfer';$('#destination-label').hidden=!transfer||editing;$('#tx-cat-label').hidden=['income','transfer'].includes($('#tx-kind').value);$('#tx-help').textContent=transfer?(editing?'This edits one imported transfer row. Keep its signed amount; mark the counterpart on the other account as a transfer too.':'A transfer creates linked entries in both accounts and is excluded from spending. Enter a positive amount leaving the source account.'):'Enter a positive amount. Refunds reduce spending in the selected category.';}
function openTransaction(id){if(!state.accounts.length){setView('accounts');notify('Add an account first.');return;}const form=$('#tx-form');form.reset();form.elements.id.value='';form.elements.date.value=localDay();form.elements.account_id.value=state.accounts[0].id;$('#tx-title').textContent=id?'Edit transaction':'Add transaction';if(id){const tx=transactionRows().find(t=>t.id===id);for(const key of ['id','date','account_id','kind','payee','category_id','note'])form.elements[key].value=tx[key]??'';form.elements.amount.value=((tx.kind==='transfer'?tx.amount:Math.abs(tx.amount))/100).toFixed(2);}txType();$('#tx-dialog').showModal();}
function mapping(){const m={skip_lines:Number($('#skip-lines').value),delimiter:$('#delimiter').value,date_format:$('#date-format').value,mode:$('#amount-mode').value,invert:$('#invert').checked,decimal_comma:$('#decimal-comma').checked};for(const k of ['date','payee','amount','debit','credit'])m[k]=$('#map-'+k).value;return m;}
function invalidatePreview(){++previewRequest;importPreview=null;$('#review').hidden=true;}
async function loadHeaders(){if(!csvText)return;const request=++headerRequest;invalidatePreview();$('#mapping').hidden=true;const {headers}=await api('/api/csv/headers','POST',{text:csvText,delimiter:$('#delimiter').value,skip_lines:Number($('#skip-lines').value)});if(request!==headerRequest)return;csvHeaders=headers;for(const key of ['date','payee','amount','debit','credit']){$('#map-'+key).innerHTML='<option value="">Not mapped</option>'+headers.map((h,i)=>`<option value="${i}">${i+1}: ${esc(h)}</option>`).join('');const patterns={date:/^date$|transaction date/i,payee:/payee|description|merchant/i,amount:/^(transaction )?amount$/i,debit:/debit|withdrawal/i,credit:/credit|deposit/i};const idx=headers.findIndex(h=>patterns[key].test(h));if(idx>=0)$('#map-'+key).value=idx;}$('#mapping').hidden=false;applyProfile();}
function updateProfileControls(){
 const selected=state.profiles.find(p=>p.name===$('#profile').value);
 const account=state.accounts.find(a=>String(a.id)===$('#import-account').value);
 for(const id of ['rename-profile','delete-profile','update-profile'])$('#'+id).disabled=!selected;
 $('#default-profile').disabled=!selected||!account||account.default_profile===selected.name;
 $('#clear-default-profile').disabled=!account?.default_profile;
 $('#profile-default-note').textContent=account?.default_profile?`Default for ${account.name}: ${account.default_profile}`:'No default format for this account. Save a new format or choose one and use it as the account default.';
}
async function selectAccountProfile(){
 importProfileAccount=$('#import-account').value;
 const account=state.accounts.find(a=>String(a.id)===importProfileAccount);
 $('#profile').value=state.profiles.some(p=>p.name===account?.default_profile)?account.default_profile:'';
 await selectProfile();
}
async function selectProfile(){
 ++headerRequest;invalidatePreview();
 const m=state.profiles.find(p=>p.name===$('#profile').value)?.mapping||{};
 $('#delimiter').value=m.delimiter||',';$('#skip-lines').value=m.skip_lines||0;
 $('#date-format').value=m.date_format||'iso';$('#amount-mode').value=m.mode||'signed';
 $('#invert').checked=!!m.invert;$('#decimal-comma').checked=!!m.decimal_comma;
 for(const key of ['date','payee','amount','debit','credit'])$('#map-'+key).value=m[key]??'';
 updateProfileControls();
 if(csvText)await loadHeaders();
}
function applyProfile(){const profile=state.profiles.find(p=>p.name===$('#profile').value);if(!profile)return;const m=profile.mapping;for(const key of ['date','payee','amount','debit','credit'])$('#map-'+key).value=m[key]??'';$('#date-format').value=m.date_format||'iso';$('#amount-mode').value=m.mode||'signed';$('#invert').checked=!!m.invert;$('#decimal-comma').checked=!!m.decimal_comma;}
function selectedSimilarGroups(rows,selected){
 const groups=new Map();
 for(const pick of selected){
  const row=rows[pick.index];
  if(row.status!=='new'||row.similar_group==null)continue;
  if(!groups.has(row.similar_group))groups.set(row.similar_group,{id:row.similar_group,tx:row.tx,count:0});
  groups.get(row.similar_group).count++;
 }
 return [...groups.values()].filter(g=>g.count>1);
}
function renderPreview(){const rows=importPreview.rows;$('#review').hidden=false;$('#review-note').textContent=`${rows.length} rows · ${rows.filter(r=>r.status==='new').length} new · ${rows.filter(r=>r.status==='possible').length} possible duplicates · ${rows.filter(r=>r.status==='duplicate'||r.status==='invalid').length} excluded. Review positive amounts for refunds and transfers.`;$('#review-body').innerHTML=rows.map(r=>r.tx?`<tr data-index="${r.index}"><td><input type="checkbox" aria-label="Include row ${r.line}" class="include-row" ${r.status==='new'?'checked':''} ${r.status==='duplicate'?'disabled':''}></td><td>${esc(r.tx.date)}<small>${esc(r.tx.payee)}</small></td><td class="number">${moneyHtml(r.tx.amount)}</td><td><select class="import-kind" aria-label="Type for row ${r.line}">${(r.tx.amount<0?['expense','transfer']:['income','refund','transfer']).map(k=>`<option value="${k}">${k}</option>`).join('')}</select></td><td><select class="import-category" aria-label="Category for row ${r.line}">${opts(state.categories,r.tx.category_id,'Uncategorized')}</select></td><td><span class="badge">${esc(r.status)}${r.similar_group!=null?' · similar new charge':''}</span></td></tr>`:`<tr><td>—</td><td>Row ${r.line}</td><td colspan="4">${esc(r.error)}</td></tr>`).join('');}
async function task(fn,button){if(button)button.disabled=true;try{await fn();}catch(e){notify(e.message);}finally{if(button)button.disabled=false;if(state&&button?.id?.includes('profile'))updateProfileControls();}}
function updateSelection(){
 const eligible=[...$('#tx-body').querySelectorAll('[data-select]:not(:disabled)')];
 $('#selection-count').textContent=`${selectedTransactions.size} selected`;
 $('#select-matches').disabled=!eligible.length;
 $('#select-matches').checked=eligible.length>0&&selectedTransactions.size===eligible.length;
 $('#select-matches').indeterminate=selectedTransactions.size>0&&selectedTransactions.size<eligible.length;
 $('#apply-category').disabled=!selectedTransactions.size||!$('#bulk-category').value;
}
$('#transaction-scope').onchange=()=>task(async()=>{
 const request=++scopeRequest,scope=$('#transaction-scope').value;$('#show-completed').checked=false;$('#category-filter').value='';
 selectedTransactions.clear();allTransactions=[];renderTransactions();syncMonthControl();
 if(scope==='all'){
  $('#tx-count').textContent='Loading all transactions…';
  try{const result=await api('/api/transactions');if(request!==scopeRequest)return;allTransactions=result.transactions;renderTransactions();}
  catch(e){if(request===scopeRequest){$('#tx-count').textContent='Could not load all transactions. Switch date range to retry.';$('#tx-body').replaceChildren();}throw e;}
 }
});
$('#tx-body').onchange=e=>{const input=e.target.closest('[data-select]');if(!input||input.disabled)return;const id=Number(input.dataset.select);if(input.checked)selectedTransactions.add(id);else selectedTransactions.delete(id);updateSelection();};
$('#select-matches').onchange=e=>{selectedTransactions.clear();$('#tx-body').querySelectorAll('[data-select]:not(:disabled)').forEach(input=>{input.checked=e.target.checked;if(input.checked)selectedTransactions.add(Number(input.dataset.select));});updateSelection();};
$('#show-completed').onchange=()=>{$('#category-filter').value='';renderTransactions();};
$('#bulk-category').onchange=updateSelection;
$('#apply-category').onclick=async e=>{
 const button=e.currentTarget,ids=[...selectedTransactions],value=$('#bulk-category').value;
 if(!ids.length||!value)return;
 if(ids.length>5000){notify('Select at most 5,000 transactions at a time. Narrow the search or category filter.');return;}
 const label=value==='none'?'Uncategorized':state.categories.find(c=>String(c.id)===value)?.name;
 if(!confirm(`Assign ${ids.length} selected transactions to ${label}? Their existing categories will be replaced.`))return;
 await task(async()=>{const result=await api('/api/transactions/category','POST',{ids,category_id:value==='none'?null:Number(value)});selectedTransactions.clear();await refresh();notify(`${result.updated} transactions categorized.`);},button);
 updateSelection();
};
async function renderUsers(){
 $('#profile-identity').textContent=`Signed in as ${state.user.username}${state.user.is_admin?' · Administrator':''}`;
 $('#user-admin').hidden=!state.user.is_admin;
 $('#users-list').replaceChildren();$('#manage-user').replaceChildren();
 if(!state.user.is_admin)return;
 const {users}=await api('/api/users');
 $('#users-list').innerHTML=users.map(u=>`<div class="account-row"><span>${esc(u.username)}</span><small>${u.is_admin?'Administrator':u.enabled?'Active':'Disabled'}</small></div>`).join('');
 $('#manage-user').innerHTML=opts(users.filter(u=>!u.is_admin).map(u=>({id:u.id,name:u.username})));
}
$('#password-form').onsubmit=e=>{e.preventDefault();task(async()=>{await api('/api/password','POST',Object.fromEntries(new FormData(e.target)));e.target.reset();$('#shell').hidden=true;$('#login').hidden=false;clearPrivateState();notify('Password changed. Sign in with your new password.');},e.submitter);};
$('#user-form').onsubmit=e=>{e.preventDefault();task(async()=>{await api('/api/users','POST',Object.fromEntries(new FormData(e.target)));e.target.reset();await renderUsers();notify('User created. Share the login details privately.');},e.submitter);};
$('#user-action').onchange=()=>{const reset=$('#user-action').value==='reset_password';$('#delete-user-warning').hidden=$('#user-action').value!=='delete';$('#reset-password-label').hidden=!reset;$('#reset-password').required=reset;$('#reset-password').value='';};
$('#manage-user-form').onsubmit=e=>{e.preventDefault();task(async()=>{const data=Object.fromEntries(new FormData(e.target));if(data.action==='delete'){
 const username=$('#manage-user').selectedOptions[0]?.textContent;
 if(!data.user_id||!username)throw Error('Select a user to delete.');
 const confirmation=prompt(`Permanently delete ${username}? This deletes all their saved transactions, accounts, categories, merchant rules, and CSV mappings. This cannot be undone.\n\nType ${username} exactly to confirm:`);
 if(confirmation===null)return;
 if(confirmation!==username)throw Error('Username did not match. Nothing was deleted.');
 await api('/api/users/'+data.user_id,'DELETE',{confirm_username:confirmation});
}else{
 if(!confirm('Apply this change to the selected user?'))return;
 await api('/api/users/'+data.user_id,'POST',{action:data.action,password:data.password});
}
$('#reset-password').value='';await renderUsers();notify(data.action==='delete'?'User and saved financial data deleted.':'User updated.');},e.submitter);};
function showSetup(questions){
 clearPrivateState();$('#login').hidden=true;$('#shell').hidden=true;$('#account-setup').hidden=false;
 $('#setup-questions').innerHTML=questions.map((q,i)=>`<label>${esc(q)}<input name="answer${i}" type="password" maxlength="256" autocomplete="off" required></label>`).join('');
}
function backToLogin(){
 recoveryToken='';resetToken='';
 for(const id of ['recovery-start','recovery-verify','recovery-reset'])$('#'+id).reset();
 $('#recovery-questions').replaceChildren();$('#recovery-error').textContent='';
 $('#recovery').hidden=true;$('#account-setup').hidden=true;$('#shell').hidden=true;$('#login').hidden=false;
}
$('#setup-signout').onclick=()=>task(async()=>{await api('/api/logout','POST',{});clearPrivateState();backToLogin();});
$('#setup-form').onsubmit=e=>{e.preventDefault();task(async()=>{
 const f=e.target.elements;if(f.password.value!==f.confirm.value)throw Error('The passwords do not match.');
 await api('/api/complete-setup','POST',{new_password:f.password.value,answers:[0,1,2].map(i=>f['answer'+i].value)});
 e.target.reset();backToLogin();notify('Account setup complete. Sign in with your chosen password.');
},e.submitter);};
$('#forgot-password').onclick=()=>{backToLogin();$('#login').hidden=true;$('#recovery').hidden=false;$('#recovery-start').hidden=false;$('#recovery-verify').hidden=true;$('#recovery-reset').hidden=true;};
$('#recovery-back').onclick=backToLogin;
$('#recovery-start').onsubmit=e=>{e.preventDefault();task(async()=>{
 $('#recovery-error').textContent='';const result=await api('/api/recovery/start','POST',{username:e.target.elements.username.value});
 recoveryToken=result.token;resetToken='';$('#recovery-start').hidden=true;$('#recovery-verify').hidden=false;
 $('#recovery-questions').innerHTML=result.questions.map(q=>`<label>${esc(q.text)}<input name="${q.id}" type="password" maxlength="256" autocomplete="off" required></label>`).join('');
},e.submitter);};
$('#recovery-verify').onsubmit=e=>{e.preventDefault();task(async()=>{
 try{
  const result=await api('/api/recovery/verify','POST',{token:recoveryToken,answers:Object.fromEntries(new FormData(e.target))});
  resetToken=result.reset_token;$('#recovery-verify').hidden=true;$('#recovery-reset').hidden=false;
 }catch(error){$('#recovery-error').textContent=error.message;$('#recovery-start').hidden=false;$('#recovery-verify').hidden=true;}
 finally{recoveryToken='';e.target.reset();}
},e.submitter);};
$('#recovery-reset').onsubmit=e=>{e.preventDefault();task(async()=>{
 const f=e.target.elements;if(f.password.value!==f.confirm.value)throw Error('The passwords do not match.');
 await api('/api/recovery/reset','POST',{reset_token:resetToken,new_password:f.password.value});backToLogin();notify('Password reset. Sign in with your new password.');
},e.submitter);};
$('#login-form').onsubmit=e=>{e.preventDefault();task(async()=>{await api('/api/login','POST',{username:e.target.username.value,password:e.target.password.value});e.target.reset();await refresh();},e.submitter);};
$('#logout').onclick=()=>task(async()=>{await api('/api/logout','POST',{});clearPrivateState();$('#shell').hidden=true;$('#login').hidden=false;});
$('nav').onclick=e=>{const b=e.target.closest('[data-view]');if(b)setView(b.dataset.view);};
$('#month').onchange=()=>{if($('#month').value)task(refresh);};$('#search').oninput=renderTransactions;$('#category-filter').onchange=renderTransactions;
$('#category-list').onclick=e=>{const b=e.target.closest('[data-category]');if(b){scopeRequest++;$('#transaction-scope').value='month';$('#category-filter').value=b.dataset.category;$('#search').value='';renderTransactions();setView('transactions');}};
$('#add-transaction').onclick=()=>openTransaction();$('#close-dialog').onclick=()=>$('#tx-dialog').close();$('#tx-kind').onchange=()=>{const id=Number($('#tx-form').elements.id.value);if(id){const old=transactionRows().find(t=>t.id===id);if(old)$('#tx-form').elements.amount.value=(($('#tx-kind').value==='transfer'?old.amount:Math.abs(old.amount))/100).toFixed(2);}txType();};
$('#tx-form').onsubmit=e=>{e.preventDefault();task(async()=>{const data=Object.fromEntries(new FormData(e.target));await api('/api/transactions',data.id?'PUT':'POST',data);$('#tx-dialog').close();await refresh();notify('Transaction saved.');},e.submitter);};
$('#tx-body').onclick=e=>{const edit=e.target.closest('[data-edit]'),del=e.target.closest('[data-delete]');if(edit)openTransaction(Number(edit.dataset.edit));if(del){const tx=transactionRows().find(t=>t.id===Number(del.dataset.delete));if(confirm(tx.transfer_id?'Delete both sides of this linked transfer?':'Delete this transaction?'))task(async()=>{await api('/api/transactions/'+tx.id,'DELETE',{});await refresh();});}};
for(const [form,path] of [['account-form','accounts'],['category-form','categories'],['rule-form','rules']])$('#'+form).onsubmit=e=>{e.preventDefault();task(async()=>{await api('/api/'+path,'POST',Object.fromEntries(new FormData(e.target)));e.target.reset();await refresh();notify('Saved.');},e.submitter);};
function previewOpeningBalance(){
 const form=$('#account-edit-form'),account=state.accounts.find(a=>a.id===Number(form.elements.id.value));
 if(!account)return;
 const opening=$('#account-edit-opening').valueAsNumber,activity=account.balance-account.opening;
 $('#account-balance-preview').innerHTML=Number.isFinite(opening)?`Recorded activity: ${moneyHtml(activity)} · Resulting balance: ${moneyHtml(Math.round(opening*100)+activity)}`:'Enter a valid opening balance.';
}
$('#account-list').onclick=e=>{const button=e.target.closest('[data-edit-opening]');if(!button)return;const a=state.accounts.find(a=>a.id===Number(button.dataset.editOpening));$('#account-edit-form').elements.id.value=a.id;$('#account-edit-title').textContent=`${a.name} — opening balance`;$('#account-edit-opening').value=(a.opening/100).toFixed(2);previewOpeningBalance();$('#account-edit-dialog').showModal();};
$('#account-edit-opening').oninput=previewOpeningBalance;
$('#close-account-edit').onclick=()=>$('#account-edit-dialog').close();
$('#account-edit-form').onsubmit=e=>{e.preventDefault();task(async()=>{const data=Object.fromEntries(new FormData(e.target));await api('/api/accounts/'+data.id,'PUT',{opening:data.opening});$('#account-edit-dialog').close();await refresh();notify('Opening balance updated.');},e.submitter);};
$('#category-chips').onclick=e=>{const b=e.target.closest('[data-edit-category]');if(!b)return;const cat=state.categories.find(c=>c.id===Number(b.dataset.editCategory));$('#category-edit-form').elements.id.value=cat.id;$('#category-edit-name').value=cat.name;$('#category-edit-title').textContent=`Edit ${cat.name}`;$('#replacement-category').innerHTML=opts(state.categories.filter(c=>c.id!==cat.id),'','Uncategorized');$('#category-dialog').showModal();};
$('#close-category').onclick=()=>$('#category-dialog').close();
$('#category-edit-form').onsubmit=e=>{e.preventDefault();task(async()=>{const data=Object.fromEntries(new FormData(e.target));await api('/api/categories/'+data.id,'PUT',{name:data.name});$('#category-dialog').close();invalidatePreview();await refresh();notify('Category renamed.');},e.submitter);};
$('#category-delete-form').onsubmit=e=>{e.preventDefault();task(async()=>{const id=$('#category-edit-form').elements.id.value,replacement=$('#replacement-category').value;if(!confirm('Delete this category and move its transactions and rules to the selected destination?'))return;await api('/api/categories/'+id,'DELETE',{replacement_id:replacement?Number(replacement):null});$('#category-dialog').close();invalidatePreview();await refresh();notify('Category deleted. Transactions were kept.');},e.submitter);};
$('#rules-list').onclick=e=>{const b=e.target.closest('[data-delete-rule]');if(b)task(async()=>{await api('/api/rules/'+b.dataset.deleteRule,'DELETE',{});await refresh();});};
$('#csv-file').onchange=()=>task(async()=>{const file=$('#csv-file').files[0];if(!file)return;if(file.size>2_000_000)throw Error('Use a CSV smaller than 2 MB.');const request=++headerRequest;invalidatePreview();csvText='';$('#mapping').hidden=true;const text=decodeCsvBytes(await file.arrayBuffer());if(request!==headerRequest)return;csvText=text;await loadHeaders();});
$('#delimiter').onchange=()=>task(loadHeaders);$('#skip-lines').onchange=()=>task(loadHeaders);
$('#profile').onchange=()=>task(selectProfile);
$('#mapping').addEventListener('change',invalidatePreview);
$('#import-account').onchange=()=>task(selectAccountProfile);
$('#save-profile').onclick=e=>task(async()=>{
 const name=$('#profile-name').value.trim();
 await api('/api/profiles','POST',{name,mapping:mapping(),account_id:$('#import-account').value});
 invalidatePreview();await refresh();$('#profile').value=name;$('#profile-name').value='';updateProfileControls();notify('CSV format saved as this account’s default.');
},e.currentTarget);
$('#update-profile').onclick=e=>task(async()=>{
 const name=$('#profile').value;if(!name)return;
 await api('/api/profiles','PUT',{original_name:name,name,mapping:mapping()});
 invalidatePreview();await refresh();notify('Saved format updated.');
},e.currentTarget);
$('#rename-profile').onclick=e=>task(async()=>{
 const original=$('#profile').value;if(!original)return;
 const name=prompt('New name for this saved format:',original);if(name===null)return;
 await api('/api/profiles','PUT',{original_name:original,name});
 invalidatePreview();await refresh();$('#profile').value=name.trim();updateProfileControls();notify('Saved format renamed.');
},e.currentTarget);
$('#delete-profile').onclick=e=>task(async()=>{
 const name=$('#profile').value;if(!name||!confirm(`Delete saved format “${name}”? Accounts using it will have no default format. Imported transactions will be kept.`))return;
 await api('/api/profiles','DELETE',{name});invalidatePreview();await refresh();await selectAccountProfile();notify('Saved format deleted.');
},e.currentTarget);
$('#default-profile').onclick=e=>task(async()=>{
 await api('/api/profile-default','PUT',{account_id:$('#import-account').value,name:$('#profile').value});
 invalidatePreview();await refresh();notify('Default CSV format saved for this account.');
},e.currentTarget);
$('#clear-default-profile').onclick=e=>task(async()=>{
 await api('/api/profile-default','PUT',{account_id:$('#import-account').value,name:null});
 invalidatePreview();await refresh();await selectAccountProfile();notify('Account default cleared.');
},e.currentTarget);
$('#preview-csv').onclick=e=>task(async()=>{const request=++previewRequest;const result=await api('/api/csv/preview','POST',{text:csvText,account_id:$('#import-account').value,mapping:mapping()});if(request!==previewRequest)return;importPreview=result;renderPreview();},e.currentTarget);
$('#commit-csv').onclick=e=>task(async()=>{if(!importPreview)throw Error('Preview the file again.');const selected=[...$('#review-body').querySelectorAll('tr[data-index]')].filter(tr=>tr.querySelector('.include-row').checked).map(tr=>({index:Number(tr.dataset.index),kind:tr.querySelector('.import-kind').value,category_id:tr.querySelector('.import-category').value,allow_possible:importPreview.rows[Number(tr.dataset.index)].status==='possible'}));if(!selected.length)throw Error('Select at least one row.');const similar=selectedSimilarGroups(importPreview.rows,selected);for(const group of similar){if(!confirm(`This import contains ${group.count} selected new transactions for “${group.tx.payee}” on ${group.tx.date}, each for ${money(group.tx.amount)}.\n\nAdd all ${group.count} as separate transactions? Choose Cancel to review your selections.`))return;}if(!confirm(`Import ${selected.length} transactions into ${state.accounts.find(a=>String(a.id)===$('#import-account').value)?.name}? Selected possible duplicates will be added as separate transactions.`))return;const result=await api('/api/csv/commit','POST',{token:importPreview.token,selected,confirmed_similar_groups:similar.map(g=>g.id)});invalidatePreview();$('#import-result').innerHTML=`<div class="panel"><strong>${result.imported} transactions imported.</strong> <button class="secondary" id="undo-import">Undo this import</button></div>`;$('#undo-import').onclick=()=>{if(confirm('Remove all transactions from this import, including any later edits to them?'))task(async()=>{await api('/api/imports/'+result.batch_id,'DELETE',{});$('#import-result').replaceChildren();await refresh();notify('Import undone.');});};await refresh();notify('Import complete. Choose the statement month to view it.');},e.currentTarget);
$('#export').onclick=()=>task(async()=>{const response=await fetch('/api/export');if(!response.ok)throw Error('Please sign in again to export.');const blob=await response.blob(),url=URL.createObjectURL(blob),a=document.createElement('a');a.href=url;a.download='spearmint-transactions.csv';a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);});
refresh().catch(e=>{if(e.message!=='Please sign in.')notify(e.message);});
