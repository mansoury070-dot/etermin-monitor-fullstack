# eTermin-Monitor (Full-Stack Edition)

A robust, containerized automation bot and monitoring system initially designed to help users secure appointments at the Ausländerbehörde in Duisburg.

During the process of migrating this project from a simple frontend script to a full-stack architecture, the Ausländerbehörde updated their system to automatically assign appointments to residents. As a result, the original primary use case for this bot was rendered obsolete.

However, the bot remains fully functional and is currently active for other highly demanded services, such as the vehicle registration office and driver's license departments. More importantly, the core engine is completely dynamic. You can easily adapt this bot for any other municipality or government office that uses the `eTermin` platform. By simply extracting their specific `webid` and adding it to the `office_collection` dictionary located in the `constants.py` file in `core` directory, the bot will seamlessly monitor and book appointments for that new office!

## Architecture & Tech Stack

The application has been heavily decoupled and rewritten into a scalable, asynchronous full-stack architecture:

* **Frontend (UI):** `Streamlit` – Now decoupled from the core logic, serving strictly as the presentation layer.
* **Backend (API):** `FastAPI` – Handles all business logic, session management, and routing asynchronously.
* **Task Queue & Active State:** `Redis` – Manages all active background polling jobs, task queues, and real-time session data. It processes user booking data strictly in-memory and wipes it instantly upon task completion, ensuring data privacy.
* **Database & Synchronization:** `Serverless PostgreSQL` (via `SQLAlchemy`) – Integrated with `Neon` for a lightweight, cloud-managed database solution. It stores core user session preferences and caches service parameters. A dedicated Python synchronization container runs daily at 3:00 AM to update these parameters and minimize redundant requests to the eTermin servers.
* **Scraping Engine:** `curl_cffi` – Used for asynchronous, TLS-impersonated HTTP requests to reliably bypass server security blocks and bot protections.
* **Infrastructure:** `Docker` & `Docker Compose` – The entire environment is fully containerized, featuring isolated containers for the UI, API, execution workers, and the daily synchronization script.

## Key Features

* **Persistent Sessions & Background Execution:** The frontend is completely decoupled. You can configure your preferences, close your browser, and the background workers will continue hunting for your appointment seamlessly.
* **Live Appointment Viewer:** Select a specific service and instantly view all currently available dates and time slots directly on the dashboard.
* **Auto-Booking Mode:** Specify your desired time range, and the bot will automatically secure the first matching appointment it finds before it disappears.
* **Telegram Notifications:** Opt to receive real-time alerts on your phone the millisecond a new slot opens up instead of auto-booking.
* **Smart Anti-Ban & Rate Limiting:** Utilizes `curl_cffi` for TLS fingerprint spoofing alongside randomized request intervals to simulate human behavior and avoid server-side blocks.
* **Privacy First:** All personal booking information is processed strictly in-memory via Redis and is permanently wiped the second the booking is completed or the session expires. No sensitive personal data is ever logged or stored in the database.


## Under The Hood

The booking website does not use direct links with visible parameters. Instead, the website's JavaScript code dynamically generates the required parameters when a user clicks on an available time. To automate this, I reverse-engineered the JavaScript code to understand exactly how and under what conditions these parameters are created. 

I then replicated this entire logic inside my Python backend. This allows the background workers to programmatically construct the payloads and execute the final booking POST requests with valid session parameters in milliseconds. *(Note: I intentionally skipped extracting the functions for online payments and modifying existing appointments, as the bot is strictly focused on quickly finding and booking new slots).*

## TODO / Upcoming Features

* **Interactive UI Booking:** Upgrade the Live Appointment Viewer to allow users to instantly secure an appointment by simply clicking on an available time slot directly within the web dashboard.

## Installation and Setup

The entire infrastructure is dockerized for a seamless setup. You do not need to install Python libraries manually on your host machine.

1. Clone this repository:
   ```bash
   git clone https://github.com/mansoury070-dot/etermin-monitor-fullstack.git
   ```

2. Navigate to the project folder:
   ```bash
   cd etermin-monitor
   ```

3. Configure the environment variables:
   Duplicate the example file:
   ```bash
   cp .env.example .env
   ```
   Open the `.env` file and fill in your necessary credentials (e.g., your Telegram bot token and Neon PostgreSQL connection string).

4. Start the application:
   ```bash
   docker-compose up -d --build
   ```

Once the containers are running, you can access the web interface by navigating to `http://localhost:8501` in your browser.

## Telegram Setup

To receive real-time notifications for available appointments, you need to configure your Telegram bot credentials:

1. **Create a Bot**: Open Telegram, search for **@BotFather**, and create a new bot to receive your `BOT_TOKEN`.

2. **Configure Environment**: Open your `.env` file and add your credentials:
  
```text
   MY_TELEGRAM_BOT_TOKEN=your_telegram_bot_token_here
```

---

## Disclaimer

This project, including the script and all associated source code, is developed and provided strictly for educational and informational purposes only. By downloading, cloning, or deploying this repository, you agree to the following terms:

* **No Liability:** The author assumes no responsibility or liability for how this code is used or deployed. Any actions taken using this architecture are solely at your own risk.
* **Source Code Modifications:** The default polling interval is hardcoded in the source code with a randomized jitter to simulate normal human behavior and prevent server overload. If you modify the source code to decrease this interval or use this bot to send aggressive automated requests, you are solely responsible for any consequences (e.g., IP bans or legal action from the target servers).
* **Terms of Service:** It is your responsibility to ensure that your use and deployment of this tool comply with the target website's Terms of Service.

Use this tool responsibly and ethically.
