const assert=require('node:assert/strict');
const {netMonthly,repayment,householdNet}=require('../web/calculations.js');
// Zero-interest amortisation and standard 5% rate against known amortisation formula.
assert.equal(repayment(300000,20,0,25),800);
assert.ok(Math.abs(repayment(300000,20,5,25)-1403.02)<1);
// Basic PAYE at £60k gross: 12,570 allowance, 37,700 taxed 20%, 9,730 taxed 40%.
const expectedTax=37700*.2+(60000-12570-37700)*.4;
const expectedNI=37700*.08+(60000-50270)*.02;
assert.ok(Math.abs(netMonthly(60000,0,0,'net','none')-(60000-expectedTax-expectedNI)/12)<.01);
assert.equal(netMonthly(0,0,0,'net','none'),0);
assert.ok(householdNet({salary1:60000,salary2:60000,sac1:1000,sac2:450,share2:500,shareMode:'net',loanPlan:'2'})>0);
console.log('JavaScript mortgage/tax calculations passed.');
