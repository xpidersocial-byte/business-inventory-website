/**
 * FBIHM Offline Sync Manager v2.0 (Ultra Reliability)
 * Handles IndexedDB, Background Sync API, and UI Communication via BroadcastChannel.
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
        // Listen for browser online event
        window.addEventListener('online', () => {
            console.log('[OfflineManager] Back online. Attempting fast sync...');
            if (typeof updateConnectivityUI === 'function') updateConnectivityUI();
            this.syncAll();
        });

        window.addEventListener('offline', () => {
            console.log('[OfflineManager] Device is offline.');
            if (typeof updateConnectivityUI === 'function') updateConnectivityUI();
        });

        // Listen for messages from the Service Worker
        SYNC_CHANNEL.onmessage = (event) => {
            if (event.data.type === 'SYNC_COMPLETE') {
                this.showSyncToast(event.data.count);
                // Optionally refresh parts of the page without reload
                if (typeof onSyncComplete === 'function') onSyncComplete(event.data);
            }
        };
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
                url,
                method,
                body: serializedBody,
                isFormData: isFormData,
                timestamp: new Date().toISOString()
            };
            
            const request = store.add(action);
            request.onsuccess = () => {
                this.showOfflineToast();
                // Attempt Background Sync registration
                this.registerBackgroundSync();
                resolve();
            };
            request.onerror = () => reject('Failed to queue action');
        });
    }

    async registerBackgroundSync() {
        if ('serviceWorker' in navigator && 'SyncManager' in window) {
            try {
                const registration = await navigator.serviceWorker.ready;
                await registration.sync.register('fbihm-sync');
                console.log('[OfflineManager] Background Sync registered');
            } catch (err) {
                console.warn('[OfflineManager] Background Sync registration failed:', err);
            }
        }
    }

    serializeFormData(formData) {
        const obj = {};
        formData.forEach((value, key) => {
            if (obj[key] !== undefined) {
                if (!Array.isArray(obj[key])) obj[key] = [obj[key]];
                obj[key].push(value);
            } else {
                obj[key] = value;
            }
        });
        return obj;
    }

    async syncAll() {
        if (!navigator.onLine || !this.db || this.syncing) return;
        
        const transaction = this.db.transaction([STORE_NAME], 'readonly');
        const store = transaction.objectStore(STORE_NAME);
        const countRequest = store.count();

        countRequest.onsuccess = async () => {
            if (countRequest.result === 0) return;
            
            this.syncing = true;
            const getAllRequest = this.db.transaction([STORE_NAME], 'readonly').objectStore(STORE_NAME).getAll();
            
            getAllRequest.onsuccess = async () => {
                const actions = getAllRequest.result;
                let successCount = 0;

                for (const action of actions) {
                    try {
                        const success = await this.executeAction(action);
                        if (success) {
                            const delTx = this.db.transaction([STORE_NAME], 'readwrite');
                            await new Promise((res) => {
                                const delReq = delTx.objectStore(STORE_NAME).delete(action.id);
                                delReq.onsuccess = res;
                            });
                            successCount++;
                        }
                    } catch (e) {
                        console.error('[OfflineManager] Sync failed for item:', action.id);
                    }
                }
                
                if (successCount > 0) {
                    this.showSyncToast(successCount);
                    // Emit local event so page can update data without reload
                    document.dispatchEvent(new CustomEvent('dataSynced', { detail: { count: successCount } }));
                }
                this.syncing = false;
            };
        };
    }

    async executeAction(action) {
        let options = {
            method: action.method,
            headers: {}
        };

        if (action.isFormData) {
            const formData = new FormData();
            for (const key in action.body) {
                if (Array.isArray(action.body[key])) {
                    action.body[key].forEach(val => formData.append(key, val));
                } else {
                    formData.append(key, action.body[key]);
                }
            }
            options.body = formData;
        } else {
            options.headers['Content-Type'] = 'application/json';
            options.body = JSON.stringify(action.body);
        }
        
        try {
            const response = await fetch(action.url, options);
            return response.ok;
        } catch (e) {
            return false;
        }
    }

    showOfflineToast() {
        if (typeof Swal !== 'undefined') {
            Swal.fire({
                toast: true, position: 'bottom-end', icon: 'info',
                title: 'Working Offline',
                text: 'Your action was saved locally and will sync automatically.',
                showConfirmButton: false, timer: 4000
            });
        }
    }

    showSyncToast(count) {
        if (typeof Swal !== 'undefined') {
            Swal.fire({
                toast: true, position: 'bottom-end', icon: 'success',
                title: 'Fast Sync Complete',
                text: `Successfully synchronized ${count} actions.`,
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
    
    const options = { method: 'POST' };
    if (data instanceof FormData) {
        options.body = data;
    } else {
        options.headers = { 'Content-Type': 'application/json' };
        options.body = JSON.stringify(data);
    }
    
    return fetch(url, options);
}
