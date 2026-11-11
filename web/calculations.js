/* England PAYE annualised estimate for 2026/27. Tax assumptions are dated.
   Transparent estimation only: do not treat as a lender or payroll quote. */
(function(root){
  'use strict';
  const STUDENT_PLANS={
    '1':[26900,.09], '2':[29385,.09], '4':[33795,.09],
    '5':[25000,.09], postgrad:[21000,.06]
  };
  function netMonthly(gross, sacrifice=0, share=0, shareMode='net', loan='none'){
    gross=Number(gross); sacrifice=Number(sacrifice); share=Number(share);
    if (![gross,sacrifice,share].every(Number.isFinite) || gross<0 || sacrifice<0 || share<0) return NaN;
    const pretax=Math.min(gross, sacrifice*12+(shareMode==='sacrifice'?share*12:0));
    const pay=gross-pretax;
    const pa=Math.max(0,12570-Math.max(0,pay-100000)/2);
    const taxable=Math.max(0,pay-pa);
    // Basic-rate BAND is £37,700 of taxable income (not increased when PA tapers).
    const tax=Math.min(taxable,37700)*.2+
      Math.min(Math.max(0,taxable-37700),87440)*.4+
      Math.max(0,taxable-125140)*.45;
    const ni=Math.min(Math.max(0,pay-12570),37700)*.08+
      Math.max(0,pay-50270)*.02;
    const rule=STUDENT_PLANS[loan];
    const student=rule?Math.max(0,pay-rule[0])*rule[1]:0;
    const postTax=shareMode==='net'?share*12:0;
    return Math.max(0,(pay-tax-ni-student-postTax)/12);
  }
  function householdNet(s){
    return netMonthly(s.salary1,s.sac1,0,'net',s.loanPlan)+
      netMonthly(s.salary2,s.sac2,s.share2,s.shareMode,'none');
  }
  function repayment(price,depositPct,ratePct,termYears){
    const values=[price,depositPct,ratePct,termYears].map(Number);
    if(!values.every(Number.isFinite)||price<0||depositPct<0||depositPct>=100||ratePct<0||termYears<=0)return NaN;
    const principal=price*(1-depositPct/100),n=termYears*12,r=ratePct/1200;
    return r===0?principal/n:principal*r/(1-Math.pow(1+r,-n));
  }
  const api={netMonthly,householdNet,repayment};
  if(typeof module!=='undefined'&&module.exports)module.exports=api;
  root.HouseMath=api;
})(typeof window!=='undefined'?window:globalThis);
