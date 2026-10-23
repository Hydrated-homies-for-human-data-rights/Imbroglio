document.addEventListener('DOMContentLoaded', async () => {
  try {
    console.log("Popup opened. Searching for domain...");

    const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
    
    if (!tab || !tab.url) {
      throw new Error("Could not read tab URL. Did you add 'tabs' to permissions?");
    }

    const url = new URL(tab.url);
    const domain = url.hostname.replace('www.', '');
    console.log("Detected domain:", domain);
    
    document.getElementById('domain-name').textContent = domain;

    chrome.runtime.sendMessage({ action: "getData", domain: domain }, (response) => {
      if (chrome.runtime.lastError) {
        console.error("Error communicating with background:", chrome.runtime.lastError);
        return;
      }

      console.log("Response from background:", response);

      if (response && response.data) {
        const siteData = response.data;
        
        const overallBadge = document.getElementById('overall-badge');
        overallBadge.textContent = siteData.overall;
        overallBadge.className = `p-badge p-${siteData.overall.toLowerCase()}`;

        const listContainer = document.getElementById('p-list');
        for (const [category, data] of Object.entries(siteData.scores)) {
          if (!data) continue;
          const level = data.level || "UNKNOWN";
          const findings = data.findings || 0;

          const row = document.createElement('div');
          row.className = 'p-row';
          row.innerHTML = `
            <div>${category}</div>
            <div class="p-right">
              <span class="p-badge p-${level.toLowerCase()}">${level}</span>
              <span class="p-findings">${findings} finding${findings !== 1 ? 's' : ""}</span>
            </div>
          `;
          listContainer.appendChild(row);
        }
      } else {
        document.getElementById('domain-name').textContent = domain;
        document.getElementById('overall-badge').style.display = 'none';
        document.getElementById('p-list').innerHTML = "<p>No privacy data found for this domain.</p>";
      }
    });
  } catch (error) {
    console.error("Popup initialization failed:", error);
  }
});