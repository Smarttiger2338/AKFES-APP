# AKFES

**Arduino Keypad-Based File Encryption System**
*A tiny file security project with an Arduino keypad, an Electron app, and just enough paranoia to make it fun.*

## What is AKFES?

AKFES is a file encryption and decryption system that uses an **Arduino keypad** as a physical password input device.

Instead of typing your password on a regular keyboard like a normal person, AKFES lets you enter it through a hardware keypad connected to an Arduino. The client app sends the file and password to the server, and the server handles license verification, encryption, and decryption.

Because apparently clicking “Encrypt” was not dramatic enough.

## Features

* Arduino keypad-based password input
* Electron desktop client
* Separate client and server structure
* License key login system
* Time-limited license keys
* Session-token-based requests
* AES-GCM file encryption
* PBKDF2 key derivation
* Works with all file extensions
* Keeps Korean filenames intact
* Adds `[암호화됨]` and `[복호화됨]` to filenames
* Green LED on success
* Red LED on failure
* Server-side rate limiting
* Revoked license key list
* Basic forensic logging
* Contact links for Telegram, GitHub, and Instagram
* JavaScript obfuscation support

## Project Structure

```text
AKFES
├─ AKFES-Server
│  ├─ server
│  │  ├─ server.py
│  │  └─ requirements.txt
│  ├─ tools
│  │  └─ generate_license_key.py
│  ├─ START_SERVER.bat
│  ├─ GENERATE_KEY.bat
│  ├─ GENERATE_KEY_QUICK.bat
│  └─ revoked_keys.json
│
├─ AKFES-Client
│  ├─ electron
│  │  ├─ main.js
│  │  ├─ preload.js
│  │  ├─ use-obfuscated.js
│  │  └─ use-original.js
│  ├─ client
│  │  ├─ templates
│  │  │  └─ index.html
│  │  └─ static
│  │     ├─ app.js
│  │     ├─ contact_config.js
│  │     ├─ style.css
│  │     └─ images
│  ├─ arduino
│  │  └─ project.ino
│  └─ START_ELECTRON_DEV.bat
│
├─ START_AKFES_ALL.bat
├─ START_AKFES_DEMO.bat
├─ GENERATE_DEMO_KEY.bat
└─ README.md
```

## How It Works

```text
1. Admin generates a time-limited license key.
2. User opens the Electron client.
3. User logs in with the license key.
4. Server verifies the license key signature and expiration time.
5. Server issues a session token.
6. User selects a file.
7. User enters a password using the Arduino keypad.
8. Client sends the file, password, and session token to the server.
9. Server encrypts or decrypts the file.
10. User downloads the result.
11. Green LED means success.
12. Red LED means something went wrong. Probably your fault. Probably.
```

## Tech Stack

### Client

* HTML
* CSS
* JavaScript
* Electron
* Web Serial API

### Server

* Python
* Flask
* Flask-CORS
* Flask-Limiter
* cryptography

### Hardware

* Arduino Uno
* 4x4 keypad
* Green LED
* Red LED
* MB102 breadboard
* Wires, patience, and at least one moment of regret

## Encryption Design

AKFES uses **AES-GCM** for file encryption.

The password entered through the Arduino keypad is not used directly as the encryption key. Instead, it is processed using **PBKDF2** to derive a stronger encryption key.

Encrypted files are stored in this format:

```text
salt 16 bytes + nonce 12 bytes + ciphertext
```

There is no obvious magic header like:

```text
HELLO_I_AM_ENCRYPTED_WITH_THIS_LIBRARY
```

because that would be rude to security.

## Filename Rules

Example:

```text
photo.png → photo[암호화됨].png
photo[암호화됨].png → photo[복호화됨].png
```

Yes, it supports Korean filenames.
Yes, that was intentional.
Yes, encoding bugs were harmed during development.

## Running the Server

Set environment variables first:

```bat
set LICENSE_SECRET=your_long_random_license_secret
set SESSION_SECRET=your_long_random_session_secret
```

Then start the server:

```bat
cd AKFES-Server
START_SERVER.bat
```

By default, the server runs at:

```text
http://127.0.0.1:5000
```

For real deployment, please use HTTPS.
Sending keys, tokens, files, and passwords over plain HTTP is how horror stories begin.

## Running the Client

```bat
cd AKFES-Client
set AKFES_SERVER_URL=http://127.0.0.1:5000
START_ELECTRON_DEV.bat
```

The Electron app will open, and you can log in with a license key, connect your Arduino, choose a file, and encrypt or decrypt it.

## One-Click Development Launch

For local development or demonstration:

```text
START_AKFES_ALL.bat
```

This starts both the server and the Electron client.

## Demo Mode

For quick testing:

```text
START_AKFES_DEMO.bat
```

Demo mode uses fixed demo secrets.

Do not use demo secrets in production unless you enjoy being the main character in your own incident report.

## Generating a Demo License Key

```text
GENERATE_DEMO_KEY.bat
```

Or manually:

```bat
cd AKFES-Server
set LICENSE_SECRET=your_long_random_license_secret
GENERATE_KEY_QUICK.bat 1d demo
```

Lifetime examples:

```text
3h = 3 hours
1d = 1 day
2w = 2 weeks
3m = 3 months
1y = 1 year
```

## Arduino Wiring

Default wiring:

```text
Keypad 8 wires → Arduino D2 ~ D9
Green LED      → D10
Red LED        → D11
GND            → Breadboard GND rail
```

LED wiring:

```text
D10 → resistor → green LED long leg (+)
green LED short leg (-) → GND

D11 → resistor → red LED long leg (+)
red LED short leg (-) → GND
```

Use a **220Ω ~ 330Ω resistor**.

Do not connect LEDs directly unless you want to convert electronics into tiny sadness.

## Security Notes

AKFES includes:

* Client/server separation
* License key verification
* Session token validation
* License expiration checks
* Revoked license key support
* Rate limiting
* AES-GCM authenticated encryption
* PBKDF2 key derivation
* Simplified server error messages
* Login and file-processing logs
* JavaScript obfuscation support

However:

* Obfuscation is not real security.
* Client-side code can always be inspected eventually.
* Server secrets must never be shipped to users.
* Production deployments should use HTTPS.
* Do not log passwords, full tokens, full license keys, or file contents.

Security is not a button.
Unfortunately.

## JavaScript Obfuscation

To obfuscate the client JavaScript:

```bash
cd AKFES-Client
npm install
npm run obfuscate
npm run use-obfuscated
```

To switch back to the original file:

```bash
npm run use-original
```

Obfuscation makes analysis harder, not impossible.
Think of it as locking your diary, not building Fort Knox.

## Forensic Logging

The server can log events such as:

* Successful login
* Failed login
* Revoked key usage
* Successful file processing
* Failed file processing
* Request IP address
* Error timestamps

These logs can be useful for basic forensic analysis.

Do not log:

```text
passwords
full session tokens
full license keys
file contents
```

Future-you will thank present-you.

## Why This Project Exists

AKFES started as a file encryption project and slowly evolved into a small security system involving:

* IoT-style hardware input
* Server-side authentication
* License-based access control
* Electron desktop UI
* Forensic logging
* LEDs that judge your success or failure

It is a learning project for exploring file security, hardware interaction, and practical security architecture.

## Disclaimer

This project is built for learning, experimentation, and portfolio purposes.

Before using anything like this in production, you should add:

* HTTPS
* proper server deployment
* stronger key management
* secure logging
* user privacy controls
* backup and recovery planning
* threat modeling
* probably coffee

## License

This project is for educational and research purposes.

Use responsibly.
Encrypt wisely.
Do not anger the Arduino.
