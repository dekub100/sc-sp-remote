const os = require('os');
const fs = require('fs');
const path = require('path');
const { execSync } = require('child_process');

const spicetifyRemotePath = __dirname;

function checkDependencies() {
  console.log('Checking for required dependencies...');
  try {
    execSync('git --version');
    execSync('npm --version');
    execSync('spicetify --version');
    console.log('All dependencies found.');
  } catch (error) {
    console.error('An error was found during the dependency check.');
    console.error('Please make sure git, npm, and spicetify-cli are installed and in your PATH.');
    process.exit(1);
  }
}

function installNpmDependencies() {
  console.log('Installing Node.js dependencies with npm...');
  try {
    execSync('npm install', { stdio: 'inherit' });
  } catch (error) {
    console.error('The \'npm install\' command failed.');
    process.exit(1);
  }
}

function getSpicetifyExtensionsPath() {
  console.log('Finding Spicetify extensions folder...');
  let extensionsPath;
  if (os.platform() === 'win32') {
    extensionsPath = path.join(os.homedir(), 'AppData', 'Roaming', 'spicetify', 'Extensions');
  } else {
    extensionsPath = path.join(os.homedir(), '.config', 'spicetify', 'Extensions');
  }

  if (!fs.existsSync(extensionsPath)) {
    console.error('Could not automatically find Spicetify extensions folder.');
    process.exit(1);
  }

  console.log(`Spicetify extensions folder found at: ${extensionsPath}`);
  return extensionsPath;
}

function copyExtensionFile(extensionsPath) {
  console.log('Moving remoteVolume.js to the extensions folder...');
  const source = path.join(spicetifyRemotePath, 'remoteVolume.js');
  const dest = path.join(extensionsPath, 'remoteVolume.js');
  fs.copyFileSync(source, dest);
}

function configureSpicetify() {
  console.log('Configuring Spicetify to use the extension...');
  execSync('spicetify config extensions remoteVolume.js');
  execSync('spicetify apply');
}

function installService() {
  console.log('Installing the server as a service...');
  const platform = os.platform();

  if (platform === 'win32') {
    const { Service } = require('node-windows');
    const svc = new Service({
      name: 'SpicetifyRemoteServer',
      description: 'Spicetify Remote Server',
      script: path.join(spicetifyRemotePath, 'volume-server.js'),
    });

    svc.on('install', () => {
      svc.start();
      console.log('Service installed and started.');
    });

    svc.install();
  } else if (platform === 'linux') {
    const { Service } = require('node-linux');
    const svc = new Service({
      name: 'SpicetifyRemoteServer',
      description: 'Spicetify Remote Server',
      script: path.join(spicetifyRemotePath, 'volume-server.js'),
    });

    svc.on('install', () => {
      svc.start();
      console.log('Service installed and started.');
    });

    svc.install();
  } else if (platform === 'darwin') {
    const { Service } = require('node-mac');
    const svc = new Service({
      name: 'SpicetifyRemoteServer',
      description: 'Spicetify Remote Server',
      script: path.join(spicetifyRemotePath, 'volume-server.js'),
    });

    svc.on('install', () => {
      svc.start();
      console.log('Service installed and started.');
    });

    svc.install();
  } else {
    console.warn('Service installation is not supported on this platform.');
  }
}

function removeService() {
  console.log('Removing the service...');
  const platform = os.platform();

  if (platform === 'win32') {
    const { Service } = require('node-windows');
    const svc = new Service({
      name: 'SpicetifyRemoteServer',
      script: path.join(spicetifyRemotePath, 'volume-server.js'),
    });

    svc.on('uninstall', () => {
      console.log('Service uninstalled.');
    });

    svc.uninstall();
  } else if (platform === 'linux') {
    const { Service } = require('node-linux');
    const svc = new Service({
      name: 'SpicetifyRemoteServer',
      script: path.join(spicetifyRemotePath, 'volume-server.js'),
    });

    svc.on('uninstall', () => {
      console.log('Service uninstalled.');
    });

    svc.uninstall();
  } else if (platform === 'darwin') {
    const { Service } = require('node-mac');
    const svc = new Service({
      name: 'SpicetifyRemoteServer',
      script: path.join(spicetifyRemotePath, 'volume-server.js'),
    });

    svc.on('uninstall', () => {
      console.log('Service uninstalled.');
    });

    svc.uninstall();
  } else {
    console.warn('Service removal is not supported on this platform.');
  }
}

function main() {
  const args = process.argv.slice(2);

  if (args.includes('--install-service')) {
    installService();
    return;
  }

  if (args.includes('--remove-service')) {
    removeService();
    return;
  }

  checkDependencies();
  installNpmDependencies();
  const extensionsPath = getSpicetifyExtensionsPath();
  copyExtensionFile(extensionsPath);
  configureSpicetify();

  console.log('Installation complete! You can now test it with \'node volume-server.js\' from this directory.');
}

main();
