/**
 * FBIHM Offline Sync Manager v2.2 (Persistent UI)
 * Added: Methods to retrieve pending data for persistent offline display.
 */

const DB_NAME = 'xpider_offline_db';
const DB_VERSION = 1;
const STORE_NAME = 'pending_syncs';
const SYNC_CHANNEL = new BroadcastChannel('offline_sync_status');

class OfflineManager {
    constructor() {
        this.db = null;
        this.syncing = false;
        this.initDB();
        this.setupEventListeners();
    }

    async initDB() {
        return new Promise((resolve, reject) => {
            const request = indexedDB.open(DB_NAME, DB_VERSION);
            request.onerror = (e) => reject('IndexedDB error: ' + e.target.errorCode);
            request.onsuccess = (e) => {
                this.db = e.target.result;
                resolve(this.db);
                if (navigator.onLine) this.syncAll();
            };
            request.onupgradeneeded = (e) => {
                const db = e.target.result;
                if (!db.objectStoreNames.contains(STORE_NAME)) {
                    db.createObjectStore(STORE_NAME, { keyPath: 'id', autoIncrement: true });
                }
            };
        });
    }

    setupEventListeners() {
        window.addEventListener('online', () => {
            if (typeof updateConnectivityUI === 'function') updateConnectivityUI();
            this.syncAll();
        });
        window.addEventListener('offline', () => {
            if (typeof updateConnectivityUI === 'function') updateConnectivityUI();
        });
        SYNC_CHANNEL.onmessage = (event) => {
            if (event.data.type === 'SYNC_COMPLETE') {
                this.showSyncToast(event.data.count);
                document.dispatchEvent(new CustomEvent('dataSynced', { detail: event.data }));
            }
        };
    }

    /**
     * Retrieve all pending actions for a specific page/URL
     */
    async getPendingByUrl(urlPart) {
        if (!this.db) await this.initDB();
        return new Promise((resolve) => {
            const tx = this.db.transaction([STORE_NAME], 'readonly');
            const store = tx.objectStore(STORE_NAME);
            const request = store.getAll();
            request.onsuccess = () => {
                const results = request.result.filter(action => action.url.includes(urlPart));
                resolve(results);
            };
        });
    }

    async queueAction(url, method, body) {
        if (!this.db) await this.initDB();
        return new Promise((resolve, reject) => {
            const transaction = this.db.transaction([STORE_NAME], 'readwrite');
            const store = transaction.objectStore(STORE_NAME);
            
            let serializedBody = body;
            let isFormData = false;
            
            if (body instanceof FormData) {
                serializedBody = this.serializeFormData(body);
                isFormData = true;
            }

            const action = {
                url, method, body: serializedBody, isFormData: isFormData,
                timestamp: new Date().toISOString()
            };
            
            store.add(action).onsuccess = () => {
                this.showOfflineToast();
                this.registerBackgroundSync();
                resolve();
            };
        });
    }

    async registerBackgroundSync() {
        if ('serviceWorker' in navigator && 'SyncManager' in window) {
            const reg = await navigator.serviceWorker.ready;
            reg.sync.register('fbihm-sync').catch(() => {});
        }
    }

    serializeFormData(formData) {
        const obj = {};
        formData.forEach((value, key) => {
            if (obj[key] !== undefined) {
                if (!Array.isArray(obj[key])) obj[key] = [obj[key]];
                obj[key].push(value);
            } else { obj[key] = value; }
        });
        return obj;
    }

    async syncAll() {
        if (!navigator.onLine || !this.db || this.syncing) return;
        this.syncing = true;
        
        const actions = await new Promise(r => {
            const tx = this.db.transaction([STORE_NAME], 'readonly');
            tx.objectStore(STORE_NAME).getAll().onsuccess = (e) => r(e.target.result);
        });

        if (actions && actions.length > 0) {
            let successCount = 0;
            for (const action of actions) {
                const success = await this.executeAction(action);
                if (success) {
                    const delTx = this.db.transaction([STORE_NAME], 'readwrite');
                    delTx.objectStore(STORE_NAME).delete(action.id);
                    successCount++;
                }
            }
            if (successCount > 0) {
                this.showSyncToast(successCount);
                // Important: reload after sync to get official IDs from server
                setTimeout(() => window.location.reload(), 2000);
            }
        }
        this.syncing = false;
    }

    async executeAction(action) {
        let options = { method: action.method, headers: {} };
        if (action.isFormData) {
            const fd = new FormData();
            for (const k in action.body) {
                if (Array.isArray(action.body[k])) action.body[k].forEach(v => fd.append(k, v));
                else fd.append(k, action.body[k]);
            }
            options.body = fd;
        } else {
            options.headers['Content-Type'] = 'application/json';
            options.body = JSON.stringify(action.body);
        }
        try {
            const res = await fetch(action.url, options);
            return res.ok;
        } catch (e) { return false; }
    }

    showOfflineToast() {
        if (typeof Swal !== 'undefined') {
            Swal.fire({
                toast: true, position: 'bottom-end', icon: 'info',
                title: 'Saved Locally', text: 'Data is safe and will sync later.',
                showConfirmButton: false, timer: 3000
            });
        }
    }

    showSyncToast(count) {
        if (typeof Swal !== 'undefined') {
            Swal.fire({
                toast: true, position: 'bottom-end', icon: 'success',
                title: 'Sync Success', text: `${count} actions uploaded.`,
                showConfirmButton: false, timer: 3000
            });
        }
    }
}

const xpiderSync = new OfflineManager();

async function offlineSafePost(url, data) {
    if (!navigator.onLine) {
        await xpiderSync.queueAction(url, 'POST', data);
        return { success: true, offline: true };
    }
    try {
        const options = { method: 'POST' };
        if (data instanceof FormData) options.body = data;
        else {
            options.headers = { 'Content-Type': 'application/json' };
            options.body = JSON.stringify(data);
        }
        const response = await fetch(url, options);
        if (!response.ok) throw new Error("Server Error");
        return response;
    } catch (err) {
        await xpiderSync.queueAction(url, 'POST', data);
        return { success: true, offline: true };
    }
}
