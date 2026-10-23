// 1. Save the database as soon as the script loads (safer than onInstalled for testing)
const mockDatabase = {
    "facebook.com": {
        overall: "SEVERE",
        scores: {
            "Data Selling & Sharing": { level: "EXTENSIVE", findings: 4 },
            "Collection Scope": { level: "EXTENSIVE", findings: 2 },
            "Retention & Deletion": { level: "EXTENSIVE", findings: 4 },
            "User Rights": { level: "LIMITED", findings: 1 },
            "Security": { level: "EXTENSIVE", findings: 3 },
            "AI & Model Training": { level: "SEVERE", findings: 3 },
            "Government Requests": { level: "MODERATE", findings: 1 }
        }
    }
};

chrome.storage.local.get('privacyDatabase', (result) => {
    if (!result.privacyDatabase) {
        chrome.storage.local.set({ privacyDatabase: mockDatabase }, () => {
            console.log("imbroglio BG: Database saved to storage.");
        });
    } else {
        console.log("imbroglio BG: Database already exists in storage.");
    }
});

// 2. Listen for messages
chrome.runtime.onMessage.addListener((request, sender, sendResponse) => {
    if (request.action === "getData") {
        chrome.storage.local.get('privacyDatabase', (result) => {
            const db = result.privacyDatabase || {};
            const domain = request.domain.replace('www.', '');
            
            // Log exactly what is being requested and found
            console.log(`imbroglio BG: Requested ${domain}. Data found?`, !!db[domain]);
            
            sendResponse({ data: db[domain] || null });
        });
        return true; // Keeps the message channel open
    }
});