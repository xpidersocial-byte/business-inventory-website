/**
 * FBIHM Offline Sync Manager v4.0 (PouchDB Edition)
 * Uses PouchDB for robust synchronization and lightning-fast local data access.
 */

class OfflineSyncManager {
    constructor() {
        // Safe check for PouchDB to prevent ReferenceError: PouchDB is not defined
        const ActivePouch = window.PouchDB || (typeof PouchDB !== 'undefined' ? PouchDB : null);
        
        if (!ActivePouch) {
            console.error('❌ [OfflineManager] Critical Failure: PouchDB is not defined in any scope.');
            const mockDB = () => ({
                get: () => Promise.reject({ status: 404 }),
                put: () => Promise.resolve({ ok: true }),
                allDocs: () => Promise.resolve({ rows: [] }),
                remove: () => Promise.resolve({ ok: true }),
                info: () => Promise.resolve({ doc_count: 0 })
            });
            this.itemsDB = mockDB();
            this.syncDB = mockDB();
            this.notesDB = mockDB();
        } else {
            // Initialize PouchDB databases safely
            try {
                this.itemsDB = new ActivePouch('fbihm_items_v4');
                this.syncDB = new ActivePouch('fbihm_sync_queue_v4');
                this.notesDB = new ActivePouch('fbihm_notes_v4');
            } catch (e) {
                console.error('❌ [OfflineManager] PouchDB instantiation error:', e);
            }
        }
        
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
            const pullOk = await this.pullItems();
            const queueOk = await this.processSyncQueue();
            
            if (pullOk && queueOk) {
                console.log('✅ [OfflineManager] Full Sync Complete');
            } else {
                console.warn('⚠️ [OfflineManager] Partial sync achieved; some components failed.');
            }
        } catch (e) {
            console.error('❌ [OfflineManager] Critical sync exception:', e);
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
            if (!res.ok) {
                console.error(`❌ [OfflineManager] pullItems failed with status: ${res.status}`);
                return false;
            }
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
            return true;
        } catch (e) { 
            console.error('[OfflineManager] fetch exception while pulling items:', e);
            return false;
        }
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
        let allOk = true;
        
        for (const action of actions) {
            try {
                const ok = await this.executeRemote(action);
                if (ok) {
                    await this.syncDB.remove(action);
                } else {
                    allOk = false;
                    console.warn(`⚠️ [OfflineManager] Remote execution failed for ${action.url}`);
                }
            } catch (e) { 
                allOk = false;
                break; 
            }
        }
        return allOk;
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
