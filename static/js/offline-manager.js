/**
 * FBIHM Offline Sync Manager v4.0 (PouchDB Edition)
 * TEMPORARILY DISABLED - All actions will attempt direct network requests.
 */

class OfflineSyncManager {
    constructor() {
        // Offline features are currently disabled. All actions use direct network requests.
        const mockDB = () => ({
            get: () => Promise.reject({ status: 404 }),
            put: () => Promise.resolve({ ok: true }),
            allDocs: () => Promise.resolve({ rows: [] }),
            remove: () => Promise.resolve({ ok: true }),
            info: () => Promise.resolve({ doc_count: 0 }),
            changes: () => ({ on: () => ({ on: () => { } }) })
        });
        this.itemsDB = mockDB();
        this.syncDB = mockDB();
        this.notesDB = mockDB();
        this.isSyncing = false;
    }

    async init() { return; }
    async syncAll() { return; }
    async pullItems() { return true; }
    async queueAction(url, method, body) { 
        console.warn('Offline mode disabled. Action NOT queued.');
        return; 
    }
    async processSyncQueue() { return true; }
    async executeRemote(action) { return true; }
    serializeForm(fd) { return {}; }
    deserializeForm(obj) { return new FormData(); }
    notifyUI(type) { return; }
    async getAllItems() { return []; }
    async getPendingActions(urlFilter = '') { return []; }
}

const xpiderSync = new OfflineSyncManager();

async function offlineSafePost(url, data) {
    // ALWAYS attempt direct fetch when "offline mode" is disabled
    try {
        const headers = data instanceof FormData ? {} : { 'Content-Type': 'application/json' };
        headers['Accept'] = 'application/json';
        
        const res = await fetch(url, { 
            method: 'POST', 
            body: data instanceof FormData ? data : JSON.stringify(data),
            headers: headers
        });
        return res;
    } catch (e) {
        console.error('Network Error (Offline mode disabled):', e);
        // Return a mock failure instead of queueing
        return { ok: false, status: 503, json: async () => ({ success: false, error: 'Network unavailable' }) };
    }
}
