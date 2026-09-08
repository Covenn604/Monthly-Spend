/* Decode statement bytes before parsing or sending them to the server. */
function decodeCsvBytes(buffer) {
 const bytes = new Uint8Array(buffer);
 let encoding = 'utf-8';
 if (bytes[0] === 0xff && bytes[1] === 0xfe) encoding = 'utf-16le';
 else if (bytes[0] === 0xfe && bytes[1] === 0xff) encoding = 'utf-16be';
 else {
  // BOM-less UTF-16 exports have NULs in the high bytes of ASCII headings.
  const pairs = Math.floor(Math.min(bytes.length, 512) / 2);
  let evenZeros = 0, oddZeros = 0;
  for (let i = 0; i < pairs * 2; i += 2) {
   evenZeros += bytes[i] === 0;
   oddZeros += bytes[i + 1] === 0;
  }
  if (pairs >= 4 && oddZeros / pairs > 0.5 && evenZeros / pairs < 0.1) encoding = 'utf-16le';
  else if (pairs >= 4 && evenZeros / pairs > 0.5 && oddZeros / pairs < 0.1) encoding = 'utf-16be';
 }
 let text;
 try { text = new TextDecoder(encoding, {fatal: true}).decode(bytes); }
 catch { throw Error('Unable to decode this CSV. Save it as UTF-8 or UTF-16 and try again.'); }
 if (text.includes('\0')) throw Error('This CSV contains unexpected NUL characters. Save it as UTF-8 and try again.');
 return text;
}
if (typeof module !== 'undefined') module.exports = {decodeCsvBytes};
