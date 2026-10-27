(async function() {
    console.log("imbroglio: Content script started on", window.location.hostname);

    const domain = window.location.hostname.replace('www.', '');
    
    chrome.runtime.sendMessage({ action: "getData", domain: domain }, (response) => { 
        if (chrome.runtime.lastError) {
            console.error("imbroglio: Error: Could not communicate with background script.", chrome.runtime.lastError);
            return;
        }

        console.log("imbroglio: Response received from background:", response);

        if (response && response.data && response.data.status === "ready") {
            console.log("imbroglio: Data found! Injecting UI...");
            injectUI(domain, response.data);
        } else {
            console.log("imbroglio: No data found for this domain in the database.");
        }
    });
})();

function injectUI(domain, siteData) {
    const container = document.createElement('div');
    container.id = 'imbrolio-extension-container';

    const shadow = container.attachShadow({mode: 'open'});

    const cssUrl = chrome.runtime.getURL('styles.css');
    
    const overallLevel = siteData.overall || "UNKNOWN";

    shadow.innerHTML = `
        <link rel="stylesheet" href="${cssUrl}">

        <div id="imbrolio-extension-icon" title="View Privacy Ratings">
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="#4b5563" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                <path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"></path>
            </svg>
        </div>
        
        <div id="imbrolio-extension-modal">
            <div class="p-header">
                <h1>${domain}</h1>
                <span class="p-badge p-${overallLevel.toLowerCase()}">${overallLevel}</span>
            </div>
            <p class="p-subtitle">
                Headline = worst category, not an average.<br>
                Analyzed 2026-10-06 · Privacy Policy + Terms of Service · rubric v0.1
            </p>
            <div id="p-list"></div>
        </div>
    `;

    const listContainer = shadow.getElementById('p-list');
    const scores = siteData.scores || {};

    for (const [category, data] of Object.entries(scores)) {
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

    const icon = shadow.getElementById('imbrolio-extension-icon');
    const modal = shadow.getElementById('imbrolio-extension-modal');

    icon.addEventListener('click', (e) => {
        e.stopPropagation();
        modal.classList.toggle('active');
    });

    document.addEventListener('click', (e) => {
        if (modal.classList.contains('active') && !container.contains(e.target)) {
            modal.classList.remove('active');
        }
    });

    document.body.appendChild(container);
}