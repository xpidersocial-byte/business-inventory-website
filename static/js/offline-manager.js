/**
 * FBIHM Offline Sync Manager v4.0 (PouchDB Edition)
 * Uses PouchDB for robust synchronization and lightning-fast local data access.
 */

class OfflineSyncManager {
    constructor() {
        // Initialize PouchDB databases
        this.itemsDB = new PouchDB('fbihm_items_v4');
        this.syncDB = new PouchDB('fbihm_sync_queue_v4');
        this.notesDB = new PouchDB('fbihm_notes_v4');
        
        this.isSyncing = false;
        this.init();
    }

    async init() {
        console.log('🚀 [OfflineManager] PouchDB v4.0 Initialized');
        
        // Initial sync if online
        if (navigator.onLine) {
            this.syncAll();
        }
        
        window.addEventListener('online', () => {
            console.log('🌍 [OfflineManager] Connection restored. Syncing...');
            this.syncAll();
        });
    }

    /**
     * Complete synchronization of all data and pending actions.
     */
    async syncAll() {
        if (!navigator.onLine || this.isSyncing) return;
        this.isSyncing = true;

        try {
            await this.pullItems();
            await this.processSyncQueue();
            console.log('✅ [OfflineManager] Full Sync Complete');
        } catch (e) {
            console.error('❌ [OfflineManager] Sync failed:', e);
        } finally {
            this.isSyncing = false;
        }
    }

    /**
     * Pulls the latest items from the server and caches them locally.
     */
    async pullItems() {
        try {
            const res = await fetch('/api/items/sync');
            if (!res.ok) return;
            const items = await res.json();
            
            // Batch update PouchDB
            for (const item of items) {
                try {
                    const existing = await this.itemsDB.get(item._id);
                    item._rev = existing._rev;
                    await this.itemsDB.put(item);
                } catch (e) {
                    if (e.status === 404) await this.itemsDB.put(item);
                }
            }
            document.dispatchEvent(new CustomEvent('items_updated'));
        } catch (e) { console.warn('[OfflineManager] Could not pull items'); }
    }

    /**
     * Queues an action (POST request) for background synchronization.
     */
    async queueAction(url, method, body) {
        const action = {
            _id: 'sync_' + Date.now(),
            url,
            method,
            body: body instanceof FormData ? this.serializeForm(body) : body,
            isFormData: body instanceof FormData,
            timestamp: Date.now()
        };

        await this.syncDB.put(action);
        this.notifyUI('ACTION_QUEUED');
        
        // Trigger immediate optimistic UI update
        document.dispatchEvent(new CustomEvent('offlineActionQueued', { detail: action }));
        
        // Try background sync if available
        if ('serviceWorker' in navigator && 'SyncManager' in window) {
            const reg = await navigator.serviceWorker.ready;
            reg.sync.register('fbihm-sync').catch(() => {});
        }
    }

    async processSyncQueue() {
        const result = await this.syncDB.allDocs({ include_docs: true });
        const actions = result.rows.map(row => row.doc);
        
        for (const action of actions) {
            try {
                const ok = await this.executeRemote(action);
                if (ok) {
                    await this.syncDB.remove(action);
                }
            } catch (e) { break; }
        }
    }

    async executeRemote(action) {
        const options = { 
            method: action.method, 
            headers: action.isFormData ? {} : { 'Content-Type': 'application/json' }
        };
        options.body = action.isFormData ? this.deserializeForm(action.body) : JSON.stringify(action.body);
        
        const res = await fetch(action.url, options);
        return res.ok;
    }

    serializeForm(fd) {
        const obj = {};
        fd.forEach((val, key) => {
            if (obj[key]) {
                if (!Array.isArray(obj[key])) obj[key] = [obj[key]];
                obj[key].push(val);
            } else obj[key] = val;
        });
        return obj;
    }

    deserializeForm(obj) {
        const fd = new FormData();
        Object.keys(obj).forEach(k => {
            if (Array.isArray(obj[k])) obj[k].forEach(v => fd.append(k, v));
            else fd.append(k, obj[k]);
        });
        return fd;
    }

    notifyUI(type) {
        if (typeof Swal !== 'undefined') {
            Swal.fire({
                toast: true, position: 'bottom-end', showConfirmButton: false, timer: 3000,
                icon: type === 'SYNC_COMPLETE' ? 'success' : 'info',
                title: type === 'SYNC_COMPLETE' ? 'Synced' : 'Saved Locally'
            });
        }
    }

    /**
     * Lightning-fast local data retrieval
     */
    async getAllItems() {
        const result = await this.itemsDB.allDocs({ include_docs: true });
        return result.rows.map(row => row.doc);
    }

    async getPendingActions(urlFilter = '') {
        const result = await this.syncDB.allDocs({ include_docs: true });
        return result.rows.map(row => row.doc).filter(a => a.url.includes(urlFilter));
    }
}

const xpiderSync = new OfflineSyncManager();

async function offlineSafePost(url, data) {
    if (!navigator.onLine) {
        await xpiderSync.queueAction(url, 'POST', data);
        return { success: true, offline: true };
    }
    try {
        const res = await fetch(url, { 
            method: 'POST', 
            body: data instanceof FormData ? data : JSON.stringify(data),
            headers: data instanceof FormData ? {} : { 'Content-Type': 'application/json' }
        });
        return res;
    } catch (e) {
        await xpiderSync.queueAction(url, 'POST', data);
        return { success: true, offline: true };
    }
}
