# ❓ Frequently Asked Questions (FAQ) - Pimmich

Here are answers to frequently asked questions to help you use and troubleshoot Pimmich.

---

### General Questions

**Q: What is Pimmich?**

**A:** Pimmich is software that turns a Raspberry Pi into a smart digital photo frame. It can display photos from an [Immich](https://immich.app/) server, a USB drive, a network share (Samba/Windows), a smartphone, or the Telegram messaging app.

**Q: What do I need to use Pimmich?**

**A:** You will need:
- A Raspberry Pi (model 3, 4, or 5 recommended) with its power supply.
- An SD card with Raspberry Pi OS (64-bit) installed.
- A screen.
- An Internet connection (Wi-Fi or Ethernet).

---

### Installation and Configuration

**Q: How do I install Pimmich?**

**A:** Installation is designed to be simple:
1. Clone the GitHub repository: `git clone https://github.com/gotenash/pimmich.git`
2. Go into the project directory: `cd pimmich`
3. Make the installation script executable: `chmod +x setup.sh`
4. Run the script with administrator privileges: `sudo ./setup.sh`

The script installs the dependencies and configures the system to start automatically.

**Q: How do I access the configuration interface?**

**A:** Once the Raspberry Pi has started, open a browser on another device connected to the same network and enter the Raspberry Pi’s IP address, for example, `http://192.168.1.25`. The IP address is often shown on the frame’s screen at startup or when no photos are found.

**Q: I forgot my password for the web interface. How can I reset it?**

**A:** The easiest way to generate a new password is to rerun part of the installation script:
1. Connect to your Raspberry Pi over SSH.
2. Delete the credentials file: `sudo rm /boot/firmware/credentials.json`
3. Go to the project directory: `cd pimmich`
4. Rerun the installation script: `sudo ./setup.sh`

The script can be rerun safely. It will detect that the credentials file is missing and create a new one. The new password will be shown in the terminal when the process finishes. Make sure to save it.

**Q: How do I get an Immich API token?**

**A:**
1. Sign in to your Immich web interface.
2. Open **Account Settings** from your profile menu.
3. In the **API Keys** section, select **Generate new API Key**.
4. Give the key a name (for example, `Pimmich`) and copy the generated token.

*Tip:* For better security, create a dedicated Immich account for the frame and give it access to only one shared album.

---

### Features

**Q: How does the Telegram feature work?**

**A:** It lets you and your guests send photos directly to the frame.
1. **Create a bot** by talking to `@BotFather` on Telegram. It will give you a **token**.
2. **Get your Telegram user ID** by talking to a bot such as `@userinfobot`.
3. Enter both details in Pimmich’s **Telegram** tab.
4. Create secure, temporary invitation links for your guests.

**Q: What is the Favorites tab for?**

**A:** Mark a photo as a favorite using the star icon <i class="fas fa-star"></i> in the **Preview** tab to make it appear more often in the slideshow. Adjust the boost factor in the **Display** tab to control how often favorites appear.

**Q: What is the Postcard effect?**

**A:** It adds a white border and space for a caption to a photo, giving it the look of a postcard. Photos sent through Telegram use this effect by default.

**Q: What voice commands are available?**

**A:** After enabling voice control, start each command with the configured wake word, such as **“Magic Frame”**. Examples:

**Slideshow controls:**
- *“next photo”* / *“previous photo”*
- *“pause”* / *“resume”*

**Display controls:**
- *“set the duration to 15 seconds”*
- *“show each photo for 30 seconds”*

**Playlists and sources:**
- *“play the Vacation playlist”*
- *“show the postcards”* (starts a slideshow of Telegram photos)
- *“enable the Samba source”* / *“disable the USB source”*

**System controls:**
- *“put the display to sleep”*
- *“wake up the frame”*
- *“shut down the frame”* (shuts down the Raspberry Pi)
- *“return to the main slideshow”* (exits the current playlist and resumes the regular slideshow)

---

### Troubleshooting

**Q: I have a problem. Where can I find help?**

**A:** Start in the **System** tab and open **Logs**.
- `app.py` contains logs for the web server and configuration interface.
- `local_slideshow_stdout` and `local_slideshow_stderr` contain slideshow logs. Errors most often appear in `stderr`.

**Q: My screen does not turn off completely; the backlight stays on. What can I do?**

**A:** Some screens do not respond properly to the software sleep command (DPMS). The most reliable solution is to use a Wi-Fi smart plug to physically cut power to the screen. Pimmich can control these plugs. In the **Display** tab, enable **Smart Plug** and enter the URLs for turning the plug on and off. Many plugs, including Tasmota, Shelly, and Kasa models, can be controlled with simple HTTP requests.

**Q: Videos are not smooth or do not display. What should I do?**

**A:** In the **Display** tab, try enabling **Hardware video decoding**. It can improve performance, especially on a Raspberry Pi. If it causes problems, such as a black or blue screen after a video, disable it.

**Q: Wi-Fi will not connect, but Ethernet works. Why?**

**A:** If an Ethernet cable is connected, the system may prioritize it. In the **System** tab, try temporarily disabling the **Wired Interface (eth0)** to make the system use Wi-Fi only.

**Q: How do I update Pimmich?**

**A:** Go to the **System** tab and select **Check for updates**. Pimmich downloads the latest version from GitHub and restarts automatically.

**Q: I changed a setting, but nothing changes in the slideshow. Why?**

**A:** Some changes, especially display settings such as fonts or weather, require a slideshow restart. In the **Actions** tab, select **Stop** and then **Start Slideshow**. More substantial changes may require restarting the web app or the system from the **System** tab.
