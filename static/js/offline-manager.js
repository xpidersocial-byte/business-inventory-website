/**
 * FBIHM Offline Sync Manager v1.1
 * Handles IndexedDB storage for offline actions and automatic synchronization.
 */

const DB_NAME = 'xpider_offline_db';
const DB_VERSION = 1;
const STORE_NAME = 'pending_syncs';

class OfflineManager {
    constructor() {
        this.db = null;
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
            this.updateStatusUI(true);
            this.syncAll();
        });

        window.addEventListener('offline', () => {
            console.log('[OfflineManager] System is offline.');
            this.updateStatusUI(false);
        });
    }

    updateStatusUI(isOnline) {
        // This is now handled by templates/base.html updateConnectivityUI()
        if (typeof updateConnectivityUI === 'function') {
            updateConnectivityUI();
        }
    }

    async queueAction(url, method, body) {
        if (!this.db) await this.initDB();
        return new Promise((resolve, reject) => {
            const transaction = this.db.transaction([STORE_NAME], 'readwrite');
            const store = transaction.objectStore(STORE_NAME);
            
            // Check if body is FormData
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
            // Handle multiple values for same key if any
            if (obj[key] !== undefined) {
                if (!Array.isArray(obj[key])) {
                    obj[key] = [obj[key]];
                }
                obj[key].push(value);
            } else {
                obj[key] = value;
            }
        });
        return obj;
    }

    async syncAll() {
        if (!navigator.onLine || !this.db) return;

        const transaction = this.db.transaction([STORE_NAME], 'readwrite');
        const store = transaction.objectStore(STORE_NAME);
        const request = store.getAll();

        request.onsuccess = async () => {
            const actions = request.result;
            if (actions.length === 0) return;

            console.log(`[OfflineManager] Syncing ${actions.length} actions...`);
            
            for (const action of actions) {
                try {
                    const success = await this.executeAction(action);
                    if (success) {
                        const delTx = this.db.transaction([STORE_NAME], 'readwrite');
                        delTx.objectStore(STORE_NAME).delete(action.id);
                    }
                } catch (e) {
                    console.error('[OfflineManager] Sync failed for item:', action.id, e);
                }
            }
            
            this.showSyncToast(actions.length);
        };
    }

    async executeAction(action) {
        let options = {
            method: action.method,
            headers: {}
        };

        if (action.isFormData) {
            // Reconstruct FormData for Multipart/form-data support on backend
            const formData = new FormData();
            for (const key in action.body) {
                if (Array.isArray(action.body[key])) {
                    action.body[key].forEach(val => formData.append(key, val));
                } else {
                    formData.append(key, action.body[key]);
                }
            }
            options.body = formData;
            // Note: browser sets correct Content-Type with boundary for FormData
        } else {
            options.headers['Content-Type'] = 'application/json';
            options.body = JSON.stringify(action.body);
        }
        
        try {
            const response = await fetch(action.url, options);
            return response.ok;
        } catch (e) {
            console.error("[OfflineManager] Fetch failed during sync:", e);
            return false;
        }
    }

    showOfflineToast() {
        if (typeof Swal !== 'undefined') {
            Swal.fire({
                toast: true,
                position: 'bottom-end',
                icon: 'warning',
                title: 'Action Queued',
                text: 'System is offline. Your changes will sync automatically when reconnected.',
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
                title: 'Sync Complete',
                text: `Successfully updated ${count} actions to the server.`,
                showConfirmButton: false,
                timer: 3000
            });
        }
    }
}

// Global instance
const xpiderSync = new OfflineManager();

/**
 * Global fallback for form submissions and fetch calls
 */
async function offlineSafePost(url, formData) {
    if (!navigator.onLine) {
        console.log("[OfflineSafePost] Offline detected. Queuing action for:", url);
        await xpiderSync.queueAction(url, 'POST', formData);
        return { success: true, offline: true };
    }
    return fetch(url, { method: 'POST', body: formData });
}
