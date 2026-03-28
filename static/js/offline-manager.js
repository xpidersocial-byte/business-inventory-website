/**
 * FBIHM Offline Sync Manager v3.0 (Ultra-Sync)
 * Implements persistent UI memory and cross-tab synchronization.
 */

const DB_NAME = 'fbihm_offline_v3';
const DB_VERSION = 1;
const STORE_NAME = 'pending_actions';

class OfflineSyncManager {
    constructor() {
        this.db = null;
        this.isSyncing = false;
        this.initPromise = this.initDB();
    }

    async initDB() {
        return new Promise((resolve, reject) => {
            const request = indexedDB.open(DB_NAME, DB_VERSION);
            request.onupgradeneeded = (e) => {
                const db = e.target.result;
                if (!db.objectStoreNames.contains(STORE_NAME)) {
                    db.createObjectStore(STORE_NAME, { keyPath: 'id', autoIncrement: true });
                }
            };
            request.onsuccess = (e) => {
                this.db = e.target.result;
                console.log('✅ [OfflineManager] Database Ready');
                resolve(this.db);
            };
            request.onerror = (e) => reject(e);
        });
    }

    async queueAction(url, method, body) {
        await this.initPromise;
        return new Promise((resolve, reject) => {
            const tx = this.db.transaction([STORE_NAME], 'readwrite');
            const store = tx.objectStore(STORE_NAME);
            
            const action = {
                url, method,
                body: body instanceof FormData ? this.serializeForm(body) : body,
                isFormData: body instanceof FormData,
                timestamp: Date.now()
            };

            const req = store.add(action);
            req.onsuccess = () => {
                console.log('📦 [OfflineManager] Action Queued:', url);
                this.notifyUI('ACTION_QUEUED');
                resolve();
            };
            req.onerror = () => reject('Queue Failed');
        });
    }

    async getPendingActions(urlFilter = '') {
        await this.initPromise;
        return new Promise((resolve) => {
            const tx = this.db.transaction([STORE_NAME], 'readonly');
            const store = tx.objectStore(STORE_NAME);
            const req = store.getAll();
            req.onsuccess = () => {
                const results = req.result.filter(a => a.url.includes(urlFilter));
                console.log(`🔍 [OfflineManager] Found ${results.length} pending items for ${urlFilter}`);
                resolve(results);
            };
        });
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

    async forceSync() {
        if (!navigator.onLine || this.isSyncing) return;
        this.isSyncing = true;
        console.log('🚀 [OfflineManager] Starting Fast Sync...');
        
        const actions = await this.getPendingActions();
        if (actions.length === 0) {
            this.isSyncing = false;
            return;
        }

        let successCount = 0;
        for (const action of actions) {
            try {
                const ok = await this.executeRemote(action);
                if (ok) {
                    const tx = this.db.transaction([STORE_NAME], 'readwrite');
                    tx.objectStore(STORE_NAME).delete(action.id);
                    successCount++;
                }
            } catch (e) { console.error('Sync Error:', e); }
        }

        if (successCount > 0) {
            console.log(`✅ [OfflineManager] Successfully synced ${successCount} items.`);
            this.notifyUI('SYNC_COMPLETE', successCount);
            // Refresh to get official IDs from MongoDB
            setTimeout(() => window.location.reload(), 1500);
        }
        this.isSyncing = false;
    }

    async executeRemote(action) {
        const options = { method: action.method, headers: {} };
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
                : { icon: 'info', title: 'Saved Offline', text: 'Data will sync when connection returns.' };
            
            Swal.fire({ toast: true, position: 'bottom-end', showConfirmButton: false, timer: 3000, ...config });
        }
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
        if (!res.ok) throw new Error();
        return res;
    } catch (e) {
        await xpiderSync.queueAction(url, 'POST', data);
        return { success: true, offline: true };
    }
}

// Sync whenever connection returns
window.addEventListener('online', () => xpiderSync.forceSync());
