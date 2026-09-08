const {test} = require('node:test');
const assert = require('node:assert/strict');
const {decodeCsvBytes} = require('../static/csv-reader.js');
const text = 'Date,Description,Debit,Credit\r\n07 Sep 2026,Café 🍃,-$25.00,\r\n';
for (const encoding of ['utf8', 'utf16le', 'utf16be']) {
 for (const bom of [false, true]) {
  test(`${encoding}, BOM=${bom}`, () => {
   let bytes = Buffer.from(text, encoding === 'utf16be' ? 'utf16le' : encoding);
   if (encoding === 'utf16be') bytes.swap16();
   if (bom) bytes = Buffer.concat([Buffer.from(encoding === 'utf8' ? [239,187,191] : encoding === 'utf16le' ? [255,254] : [254,255]), bytes]);
   assert.equal(decodeCsvBytes(bytes), text);
  });
 }
}
test('malformed UTF-16 and UTF-8 are rejected', () => {
 assert.throws(() => decodeCsvBytes(Buffer.from([255,254,65])), /Unable to decode/);
 assert.throws(() => decodeCsvBytes(Buffer.from([255,254,0,216])), /Unable to decode/);
 assert.throws(() => decodeCsvBytes(Buffer.from([195,40])), /Unable to decode/);
 assert.throws(() => decodeCsvBytes(Buffer.from('Date,Description\0,Amount')), /NUL/);
});
