FROM apache/airflow:3.3.0

# soccerdata's FBref reader (via seleniumbase/undetected-chromedriver) needs a real Chrome
# binary on PATH - seleniumbase's find_chrome_executable() looks for google-chrome,
# google-chrome-stable, chrome, chromium, or chromium-browser (checked directly against the
# installed package source in the worker container). Using real Google Chrome rather than
# Chromium, matching what the project's own venv uses on the host - undetected-chromedriver
# is built to blend in as genuine Chrome, and this project already goes out of its way to
# avoid triggering FBref's bot detection (headless mode, no CAPTCHA-solve attempts), so
# switching browsers here isn't worth the risk of a different fingerprint.
USER root

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        wget \
        gnupg \
        ca-certificates \
    && wget -q -O - https://dl.google.com/linux/linux_signing_key.pub | gpg --dearmor -o /usr/share/keyrings/google-chrome-keyring.gpg \
    && echo "deb [arch=amd64 signed-by=/usr/share/keyrings/google-chrome-keyring.gpg] http://dl.google.com/linux/chrome/deb/ stable main" > /etc/apt/sources.list.d/google-chrome.list \
    && apt-get update \
    && apt-get install -y --no-install-recommends google-chrome-stable \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

USER airflow
