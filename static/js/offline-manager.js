/**
 * FBIHM Offline Sync Manager v1.2
 * Handles IndexedDB storage for offline actions and automatic synchronization.
 */

const DB_NAME = 'xpider_offline_db';
const DB_VERSION = 1;
const STORE_NAME = 'pending_syncs';

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
                // Check for sync on load if online
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
            console.log('[OfflineManager] Back online. Triggering sync...');
            if (typeof updateConnectivityUI === 'function') updateConnectivityUI();
            this.syncAll();
        });

        window.addEventListener('offline', () => {
            console.log('[OfflineManager] System is offline.');
            if (typeof updateConnectivityUI === 'function') updateConnectivityUI();
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
                url,
                method,
                body: serializedBody,
                isFormData: isFormData,
                timestamp: new Date().toISOString()
            };
            
            const request = store.add(action);
            request.onsuccess = () => {
                this.showOfflineToast();
                resolve();
            };
            request.onerror = () => reject('Failed to queue action');
        });
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
            console.log(`[OfflineManager] Syncing ${countRequest.result} actions...`);
            
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
                        console.error('[OfflineManager] Sync failed for item:', action.id, e);
                    }
                }
                
                if (successCount > 0) {
                    this.showSyncToast(successCount);
                    // Reload the page after sync to show fresh data from server
                    setTimeout(() => window.location.reload(), 3000);
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
                toast: true,
                position: 'bottom-end',
                icon: 'warning',
                title: 'Offline Action Queued',
                text: 'Changes will sync when online.',
                showConfirmButton: false,
                timer: 4000
            });
        }
    }

    showSyncToast(count) {
        if (typeof Swal !== 'undefined') {
            Swal.fire({
                toast: true,
                position: 'bottom-end',
                icon: 'success',
                title: 'Data Synchronized',
                text: `Successfully synced ${count} pending actions.`,
                showConfirmButton: false,
                timer: 3000
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
