# spicetify-remote

A spicetify extension for remote control/viewing info using websockets.

**The code was made entirely with Google Gemini so, don't ask me for any kind of help with the code because i don't know much about coding.**

## Table of Contents

- [Features](#features)
- [Requirements](#requirements)
- [Installation](#installation)
- [Usage](#usage)
- [Adding the server as a serivce in Windows (optional)](#adding-the-server-as-a-service-in-windows-optional)

## Features

- Remote control from a website or using websockets
- Remote viewing from a website
- Built in OBS Widget for streamers

## Requirements

- [node.js](https://nodejs.org/en)
- npm
- [spicetify](https://spicetify.app/)

## Installation:

1. Install [Spicetify](https://spicetify.app/docs/getting-started/#windows)
2. Clone the Repo:

   ```bash
   git clone https://github.com/dekub100/spicetify-remote
   ```

3. Navigate to the cloned repo directory:

   ```bash
   cd spicetify-remote
   ```

4. Install dependencies:

   ```bash
   npm install
   ```

5. - Move the **remoteVolume.js** file into your [extensions folder](https://spicetify.app/docs/advanced-usage/extensions#installing) in Spicetify.
   - **IMPORTANT!!! YOU WILL NEED TO REPLACE THE remoteVolume.js FILE IN THE FOLDER WITH EVERY UPDATE OF THE REPO**
6. Open a terminal and add the extension into Spicetify:

   ```bash
   spicetify config extensions remoteVolume.js
   ```

7. Apply spicetify new settings:

   ```bash
   spicetify apply
   ```

## Usage

1. Test if everything works because this is my first project with node.js

   ```bash
   node volume-server.js
   ```

2. If theres no errors open up [http://localhost:8888](http://localhost:8888) and enjoy remote [control](http://localhost:8888)/[viewing](http://localhost:8888/obs)

## Adding the server as a service in Windows (optional)

1. Download [nssm](https://nssm.cc/download)
2. Navigate to the cloned repo directory:
3. Un-zip the nssm.exe from the /win64/nssm.exe position into the root directory of the cloned repo
4. Open a terminal/cmd with administrator priviledges in the cloned repo directory
5. Install the service:

   ```bash
   nssm.exe install YourServiceName
   ```

6. Now there will be a window popup.
7. - In the **"Path"** directory select your directory where node.exe file is
   - In the **"Startup directory"** select your cloned repo directory
   - In the **"Arguments"** type in **"remoteVolume.js"**
8. Now install the service and you are good to go!
9. To remove the service if you ever need to open a terminal/cmd with administrator priviledges and type in:

   ```bash
   nssm.exe remove YourServiceName
   ```
