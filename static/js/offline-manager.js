/**
 * FBIHM Offline Sync Manager v4.0 (PouchDB Edition)
 * Uses PouchDB for robust synchronization and fast local data access.
 */

class OfflineSyncManager {
    constructor() {
        // Initialize PouchDB databases
        this.itemsDB = new PouchDB('fbihm_items');
        this.syncDB = new PouchDB('fbihm_sync_queue');
        
        this.isSyncing = false;
        this.init();
    }

    async init() {
        console.log('✅ [OfflineManager] PouchDB Initialized');
        // Initial sync of items if online
        if (navigator.onLine) {
            this.syncItems();
            this.forceSync();
        }
        
        // Listen for online event to trigger sync
        window.addEventListener('online', () => {
            this.syncItems();
            this.forceSync();
        });
    }

    /**
     * Fetches items from the server and updates the local PouchDB cache.
     */
    async syncItems() {
        if (!navigator.onLine) return;
        
        try {
            console.log('🔄 [OfflineManager] Syncing items from server...');
            const res = await fetch('/api/items/sync');
            if (!res.ok) throw new Error('Sync fetch failed');
            
            const items = await res.json();
            
            // Basic bulk update: in a real app, we'd use _rev and proper syncing,
            // but for a simple local cache, we'll just upsert.
            for (const item of items) {
                try {
                    const existing = await this.itemsDB.get(item._id);
                    item._rev = existing._rev;
                    await this.itemsDB.put(item);
                } catch (e) {
                    if (e.status === 404) {
                        await this.itemsDB.put(item);
                    } else {
                        console.error('Error syncing item:', item._id, e);
                    }
                }
            }
            console.log(`✅ [OfflineManager] ${items.length} items synced to local storage.`);
            
            // Notify UI if needed
            window.dispatchEvent(new CustomEvent('items_synced'));
        } catch (e) {
            console.warn('[OfflineManager] Item sync failed:', e);
        }
    }

    /**
     * Queues an action for later synchronization.
     */
    async queueAction(url, method, body) {
        const action = {
            _id: new Date().toJSON(), // Use timestamp as ID for ordering
            url,
            method,
            body: body instanceof FormData ? this.serializeForm(body) : body,
            isFormData: body instanceof FormData,
            timestamp: Date.now()
        };

        try {
            await this.syncDB.put(action);
            console.log('📦 [OfflineManager] Action Queued:', url);
            this.notifyUI('ACTION_QUEUED');
        } catch (e) {
            console.error('Queue Failed', e);
        }
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

    /**
     * Processes the sync queue.
     */
    async forceSync() {
        if (!navigator.onLine || this.isSyncing) return;
        this.isSyncing = true;
        
        try {
            const result = await this.syncDB.allDocs({ include_docs: true });
            const actions = result.rows.map(row => row.doc);
            
            if (actions.length === 0) {
                this.isSyncing = false;
                return;
            }

            console.log(`🚀 [OfflineManager] Syncing ${actions.length} pending actions...`);
            let successCount = 0;

            for (const action of actions) {
                try {
                    const ok = await this.executeRemote(action);
                    if (ok) {
                        await this.syncDB.remove(action);
                        successCount++;
                    }
                } catch (e) {
                    console.error('Sync Error for action:', action._id, e);
                    break; // Stop syncing to preserve order if failure occurs
                }
            }

            if (successCount > 0) {
                console.log(`✅ [OfflineManager] Successfully synced ${successCount} items.`);
                this.notifyUI('SYNC_COMPLETE', successCount);
                // Refresh occasionally to ensure UI is in sync with server IDs
                setTimeout(() => window.location.reload(), 2000);
            }
        } catch (e) {
            console.error('[OfflineManager] Sync process error:', e);
        } finally {
            this.isSyncing = false;
        }
    }

    async executeRemote(action) {
        const options = { 
            method: action.method, 
            headers: { 'X-Offline-Sync': 'true' } 
        };
        
        if (action.isFormData) {
            const fd = new FormData();
            Object.keys(action.body).forEach(k => {
                if (Array.isArray(action.body[k])) action.body[k].forEach(v => fd.append(k, v));
                else fd.append(k, action.body[k]);
            });
            options.body = fd;
        } else {
            options.headers['Content-Type'] = 'application/json';
            options.body = JSON.stringify(action.body);
        }
        
        const res = await fetch(action.url, options);
        return res.ok;
    }

    notifyUI(type, count = 0) {
        if (typeof Swal !== 'undefined') {
            const config = type === 'SYNC_COMPLETE' 
                ? { icon: 'success', title: 'Sync Complete', text: `Uploaded ${count} pending actions.` }
                : { icon: 'info', title: 'Saved Offline', text: 'Changes will sync when connection returns.' };
            
            Swal.fire({ toast: true, position: 'bottom-end', showConfirmButton: false, timer: 3000, ...config });
        }
    }

    /**
     * Helper for CSR to get all items from local DB
     */
    async getAllItems() {
        const result = await this.itemsDB.allDocs({ include_docs: true });
        return result.rows.map(row => row.doc);
    }
}

// Global instance
const xpiderSync = new OfflineSyncManager();

/**
 * Universal helper for POST requests that handles offline queueing.
 */
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
        
        if (!res.ok) throw new Error('Server returned ' + res.status);
        return res;
    } catch (e) {
        console.warn('[OfflineManager] Network call failed, queueing action:', e);
        await xpiderSync.queueAction(url, 'POST', data);
        return { success: true, offline: true };
    }
}
