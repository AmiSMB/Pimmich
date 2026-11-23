# 🖼️ Pimmich – Smart Connected Photo Frame

Pimmich is a Python application that turns a Raspberry Pi into a smart, customizable digital photo frame. It can display photos from multiple sources, be controlled by voice, and much more.

<img src="static/pimmich_logo.png" alt="Pimmich Logo" width="300" style="display: block; margin: auto;">

<p align="center">
  <a href="https://ko-fi.com/pimmich">
    <img src="https://img.shields.io/badge/Support%20on%20Ko--fi-F16061?logo=kofi&logoColor=white" alt="Support Pimmich on Ko-fi">
  </a>
</p>

---

## 📖 Table of Contents

- [✨ Main Features](#-main-features)
- [🧰 Technologies Used](#-technologies-used)
- [🚀 Installation](#-installation)
- [🔧 Configuration](#-configuration)
- [🗣️ Voice Control](#️-voice-control)
- [❓ Troubleshooting (FAQ)](#-troubleshooting-faq)
- [🛣️ Roadmap](#️-roadmap)
  - [Ideas for Future Versions](#-ideas-for-future-versions)
- [💖 Credits](#-credits)

---

## ✨ Main Features

Pimmich is packed with features for a complete, customizable experience:

#### 🖼️ **Display & Slideshow**
- **Multiple sources:** Display photos from [Immich](https://immich.app/), a network share (Samba/Windows), a USB drive, a smartphone, or Telegram.
- **Advanced customization:** Set display duration and active hours, choose transitions (fade or slide), and enable the Pan & Zoom motion effect.
- **Creative filters:** Apply filters such as Black & White, Sepia, and Vintage, as well as special effects like **Polaroid** and **Postcard**.
- **Format handling:** Portrait photos are displayed with a blurred background. Videos can play with sound and optional hardware acceleration.

#### ⚙️ **Interface & Control**
- **Comprehensive web interface:** Configure the frame locally through a password-protected page organized into groups and tabs.
- **Voice control:** Use commands such as *“Magic Frame, next photo”* or *“Magic Frame, play the Vacation playlist”*.
- **Content management:**
    - **Playlists:** Create virtual albums, reorder photos by dragging and dropping, and launch themed slideshows with a dynamic title screen showing a photo collage on a corkboard background.
    - **Favorites:** Mark photos so they appear more often.
    - **Captions:** Add custom text to photos and postcards.

#### 🌐 **Connectivity & Interactions**
- **Telegram:** Let friends and family send photos to the frame through a Telegram bot, using a secure, time-limited invitation system.
- **Wi-Fi & networking:** Configure Wi-Fi, scan for networks, and manage network interfaces from the web interface.
- **Smartphone uploads:** Import photos directly from a phone’s browser.

#### 🛠️ **Maintenance & Monitoring**
- **Easy updates:** Update Pimmich with one click from the interface.
- **Backup & restore:** Back up and restore the complete configuration.
- **System monitoring:** View Raspberry Pi temperature, CPU, RAM, and disk usage, including history graphs.
- **Detailed logs:** Access logs for each service—the web server, slideshow, and voice control—to help troubleshoot problems.

---

## 🧰 Technologies Used

- **Backend:** Python, Flask
- **Frontend:** HTML, TailwindCSS, JavaScript
- **Slideshow:** Pygame
- **Image processing:** Pillow
- **Voice control:** Picovoice Porcupine (wake word) and Vosk (speech recognition)
- **Web server:** NGINX as a reverse proxy

---

## 🚀 Installation

There are two ways to install Pimmich.

### Method 1: Pre-configured Image (Recommended)

This is the easiest way to get started.

1. **Download the current image.** Download the New Year release (v1.6.0) here: [pimmich271225.img.xz](https://github.com/gotenash/Pimmich/releases/download/v1.6.0/pimmich271225.img.xz), or visit the [Pimmich Releases page](https://github.com/gotenash/Pimmich/releases).
2. **Flash the image to an SD card.** Use Raspberry Pi Imager, BalenaEtcher, or similar software to write the downloaded image to a microSD card.
3. **Start your Raspberry Pi.** Insert the card, connect the display and power, and start the Raspberry Pi. Pimmich will launch automatically.

### Method 2: Manual Installation from the Git Repository

This method is intended for advanced users and anyone who wants to follow development closely.

#### ✅ Prerequisites

- A Raspberry Pi (model 3B+, 4, or 5 recommended) running **Raspberry Pi OS Trixie (Debian 13) Desktop, 64-bit**. This is the recommended version.
- An SD card, power supply, and display.
- An Internet connection.

#### 📝 Installation Steps

1. **Clone the repository.** Open a terminal on your Raspberry Pi and run:
   ```bash
   git clone https://github.com/gotenash/pimmich.git
   cd pimmich
   ```
2. **Run the installation script.** It installs the dependencies, configures the environment, and sets up automatic startup:
   ```bash
   chmod +x setup.sh
   sudo ./setup.sh
   ```
3. **Restart the Raspberry Pi.** Once the script finishes, restart so all services start correctly:
   ```bash
   sudo reboot
   ```

---

## 🔧 Configuration

### 1. First Connection

- At startup, the frame displays a QR code and the Raspberry Pi’s IP address.
- Scan the QR code, or open a browser on another device on the same network and enter the IP address (for example, `http://192.168.1.XX`).
- The initial password is generated during installation and stored in `/boot/firmware/credentials.json`. We strongly recommend changing it in the interface under **System > Security**.

### 2. Configure Photo Sources

- **Immich:** You will need:
    1. Your server URL (for example, `http://192.168.1.YY:2283`).
    2. An API token. In Immich, open **Account Settings > API Keys** and generate a new key. See [Get an Immich API Token](#get-an-immich-api-token) for details.
    3. The technical name of the album you want to display.
- **Samba / Windows share:** Enter the details for your network share.
- **USB:** Connect a USB drive and use the import button in the **Actions** tab.

### 3. Customize the Frame

Use the tabs to customize the frame:
- **Slideshow > Display:** Set durations, transitions, and effects.
- **Slideshow > Clock & Info:** Configure the clock, weather, and tide display.
- **Content > Sources:** Select which sources appear in the slideshow.

### Get an Immich API Token

1. Sign in to your Immich web interface and open **Account Settings**. Select your profile icon or username in the top-right corner, then choose **Account Settings**.

   ![Immich account settings](https://drive.google.com/uc?id=1_c12UZ7g8IwsL99xP55eB4qqacGAY8Kc)

2. Open the **API Key** or **API Keys** section.

   ![Immich API key menu](https://drive.google.com/uc?id=1rofAi6HNhvJbBh2D_AUsedj3HwSrQHjP)

3. Select **Generate new API Key**, give the key a name (for example, `PimmichFrame`), and create it.

   ![Generate an Immich API key](https://drive.google.com/uc?id=1HrBVgvR4UXdkhLj-4KDohufr5nt57t2G)

   ![Name the Immich API key](https://drive.google.com/uc?id=1dRBQMs0dsdM7vKlEuUzBnMmzzH3RNplc)

4. Copy the token when it appears.

   ![Copy the Immich API key](https://drive.google.com/uc?id=1hyt14hFPN3XEBu_0rh9XYIgLdXJau22y)

   ⚠️ You cannot view the token again after leaving the page. If you lose it, generate a new one. Never share it publicly; it grants access to your Immich albums.

   🔒 We recommend creating a dedicated Immich account for the frame and granting it access to only one shared album. You can add photos to that album from another account.

### Connect to Pimmich

In a browser, enter the Raspberry Pi’s IP address, for example, `http://192.168.1.XX:5000`.

![Pimmich connection screen](https://drive.google.com/uc?id=1VynC6umiYqPaln_kAb_DDd990YUkbT88)

### Configuration Page

#### Slideshow Configuration

Set how long each photo is displayed and define the hours when the slideshow runs. The display duration currently cannot be set below about 10 seconds, likely because portrait photos need time to be processed to create the blurred background.

![Slideshow configuration](https://drive.google.com/uc?id=1t_7MCKNNfHfTi5Pjc7_hDxbDzU18UvO7)

#### Photo Import Configuration

![Photo import configuration](https://drive.google.com/uc?id=1AwUgYbzGcdskt99q32VlaOc7jM303Tbd)

---

## 🗣️ Voice Control

Pimmich supports voice control in **French** and **English**.

To use a custom wake word (such as “Cadre Magique” or “Magic Frame”), you need to set up a model:
1. Create a free account in the Picovoice Console.
2. Open the **Porcupine** section and create a custom wake word.
3. Download the model for the **Raspberry Pi** platform.
4. Rename the downloaded `.ppn` file to `cadre-magique_raspberry-pi.ppn` for French or, for example, `magic-frame_raspberry-pi_en.ppn` for English.
5. Place the file in the `voice_models` folder at the root of the Pimmich project.
6. In the Pimmich interface, open the **Voice** tab, select the language, enter your Picovoice Access Key, and enable the service.

### Available Commands

After enabling voice control, start each command with the wake word **“Cadre Magique”**.

**Slideshow controls:**
- *“photo suivante”* (next photo)
- *“photo précédente”* (previous photo)
- *“pause”* / *“lecture”* (pause or resume)

**Display controls:**
- *“règle la durée à 15 secondes”* (set the duration to 15 seconds)
- *“affiche pendant 30 secondes”* (display each photo for 30 seconds)

**Playlists and sources:**
- *“lance la playlist Vacances”* (play the Vacation playlist)
- *“afficher les cartes postales”* (start a slideshow of Telegram photos)
- *“activer la source Samba”* (enable the Samba source)
- *“désactiver la source USB”* (disable the USB source)

**System controls:**
- *“passer en mode veille”* (put the display to sleep)
- *“réveiller le cadre”* (wake the frame)
- *“éteindre le cadre”* (shut down the Raspberry Pi)
- *“revenir au diaporama principal”* (leave a playlist and return to the main slideshow)

---

## ❓ Troubleshooting (FAQ)

For questions or problems, see the [English FAQ](FAQ_en.md). It covers common issues, including Wi-Fi and display problems, and offers tips for using Pimmich.

---

## 🛣️ Roadmap

> 🎂 **UPCOMING RELEASE: Birthday Edition – May 27**
> This major update marks an important step in Pimmich’s development:
> - 🚀 **More reliable updates:** The update engine in the interface is now fully operational and secure.
> - 📅 **Birthday boost:** Revisit memories with higher priority for photos taken on the same date in previous years.
> - 🌍 **Metadata & flags:** Customize the display of locations, dates, and country flags.
> - 📊 **Advanced monitoring:** New real-time graphs show the health of your Raspberry Pi.
> - 🔌 **Home automation:** Support for smart plugs to fully power off the display.
> - 🖱️ **Playlist improvements:** Organize albums with drag and drop.
> - ⚡ **Hardware acceleration:** Optimized video playback for Pi 4 and Pi 5.
> - 🔘 **Physical button:** GPIO support for controlling display sleep.

### 🗓️ Version History

> 🗓️ Starting in June 2025 — one major release each month

## ✅ August 2026 – Stability, Performance & Raspberry Pi 2/3/4/5 Compatibility

- 🚀 **Asynchronous updates and keep-alives (preventing timeouts):** Long-running tasks (Samba, Immich, and photo/video preparation) run in the background, with network pings every 10 seconds to prevent the administration interface from disconnecting.
- 🔁 **Smart incremental synchronization:** Only new media and deletions are synchronized, saving bandwidth, CPU time, and SD card wear.
- ⚡ **GPU memory (CMA) optimization:** A hidden 1×1 window (`pygame.HIDDEN`) releases GPU memory while `mpv` plays video, helping prevent crashes and slowdowns under Wayland/Sway.
- ⏱️ **Fast video playback:** Slow `ffprobe` calls were replaced with a fixed 90-second safety watchdog, so videos start in under a second.
- 📺 **Reliable video layered over the slideshow:** A selective `--ontop` option keeps video in front of the Pygame window on Pi 1 and 2.
- 🎨 **Transitions optimized for 30/60 FPS:** On Pi 1/2/3, crossfades are calculated at 50% resolution (75% fewer pixels to process) and scaled using SDL2 hardware acceleration. An FPS selector is available in the admin interface.
- 🤫 **No idle audio CPU load:** The Pygame audio mixer is initialized only when needed, avoiding background audio-server activity and saving CPU on older Pi models.
- 🌐 **Faster network handling:** Wi-Fi detection is optimized to avoid slow network calls on systems using only wired Ethernet, such as the Pi 2.
- 📦 **Optional dependencies:** HEIF/HEIC support and voice commands are optional, helping installation succeed across different system architectures. `setup.sh` handles these dependencies as needed.
- 🇫🇷 **Native French locale:** Installation configures and generates `fr_FR.UTF-8` so dates can be displayed in native French.

## ✅ May 2026

- 🚀 **Debian Trixie (Debian 13) compatibility:**
    - ✅ Complete migration to **Python 3.13**.
    - ✅ Video rendering optimized for **Sway/Wayland** (DMABUF and V4L2-copy).
    - ✅ Native Raspberry Pi 3 support on newer Linux kernels.
    - ✅ Non-interactive `sudo` commands secured with narrowly scoped rules.

## ✅ September 2025 – (Originally planned for September 15)

- 🎨 **Interface redesign:** New group and tab navigation for a clearer, more intuitive experience.
- 🎵 **Improved playlist management:**
    - ✅ A dynamic launch screen with a photo collage on a corkboard background.
    - ✅ Create virtual albums, view their contents, rename them, and start themed slideshows.
- 🔘 **Physical button:**
    - ✅ GPIO support for a physical button to put the frame to sleep and wake it.
- 🗣️ **Voice control:**
    - ✅ Added the “Cadre Magique” voice command and deeper system integration.
- 🚀 **Performance and stability:**
    - ✅ Improved responsiveness of the **System** tab through optimized log reading.
    - ✅ Improved the update script to prevent it from hanging.
    - ✅ Many bug fixes for better overall stability.

## 🛠️✅ August 2025 – Previous Version

- ✅ Video support.
- Added a thumbnail when playing a video (in the **Actions** tab).
- ✅ Added the Telegram **Postcard** feature, secured with invitation links.
- ✅ Hardware acceleration support for Pi 3.
- ✅ Added application translations (English and Spanish).
- ✅ Added a QR code for first-time connection.
- ✅ Added the Postcard effect for all photo sources.
- ✅ Added the ability to add text.
- ✅ Added a **Restart Web App** button.
- ✅ Added the **Favorites** tab, which increases the display frequency of selected photos.
- ✅ Weather and tides now show three days of forecasts.
- ✅ Bug fixes, including:
    - ✅ Display start time.
    - ✅ Reliable log deletion from the **System** tab.

## ✅ July 2025 – Current Version

- ✅ 🧭 Configure Wi-Fi from the web interface.
- ✅ 🗂️ Organize the configuration page into tabs.
- ✅ 🔁 Automatically update the Immich album at regular intervals.
- ✅ 📁 Support the SMB protocol for network photo shares.
- ✅ ⏰🌤️ Show the time and weather on the display.
- ✅ Add NGINX, so the port number (50000) is no longer needed.
- ✅ Add filters (Black & White, Sepia, Polaroid, and more).
- ✅ Add delete buttons.
- ✅ Add configuration backup.
- ✅ Add a password-change menu.
- ✅ Create `credentials.json` during setup.
- ✅ Add transition effects.
- ✅ Detect display resolution automatically.
- ✅ Import photos from a smartphone (admin and guest modes).
- ✅ Add an approval interface for photos submitted by guests.
- ✅ Show logs in the **System** tab.
- ✅ Show Raspberry Pi statistics (temperature, RAM and storage, and CPU load).

## ✅ June 2025

- ✅ Photo previews with the option to delete them.
- ✅ True display sleep, managed with `wlr-randr`.
- ✅ Set the usable screen height as a percentage.
- ✅ Correct image orientation using EXIF data and prepare images for display.

### 💡 Ideas for Future Versions

- 📱 Create an Android app to control the frame.
- Add a Pimmich remote control.
- Add Pimmich for Android TV.
- Import from Google Photos.
- Import from PhotoPrism.

---

## 💖 Credits

Pimmich project by **Gadgetaulab**.
