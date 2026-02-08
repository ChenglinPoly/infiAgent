const electron = require('electron');
console.log('type:', typeof electron);
console.log('app type:', typeof electron.app);
if (typeof electron === 'string') {
  console.log('electron is a string (path):', electron);
} else {
  console.log('keys:', Object.keys(electron).slice(0, 10));
}
process.exit(0);
