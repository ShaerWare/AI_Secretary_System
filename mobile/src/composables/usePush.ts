import { Capacitor } from "@capacitor/core";
import { PushNotifications } from "@capacitor/push-notifications";
import { LocalNotifications } from "@capacitor/local-notifications";
import { App as CapApp } from "@capacitor/app";
import { api } from "@/api/client";
import { useAuthStore } from "@/stores/auth";

let initialized = false;

/**
 * Initialize FCM push notifications:
 * - Request permission
 * - Register with APNS/FCM
 * - Send token to backend
 * - Set up listeners for foreground/tap events
 *
 * Safe to call multiple times — only initializes once per session.
 */
export async function initPush(): Promise<void> {
  if (initialized) return;
  if (!Capacitor.isNativePlatform()) return;

  const auth = useAuthStore();
  if (!auth.token) return; // wait until logged in

  initialized = true;

  try {
    // Permission
    let perm = await PushNotifications.checkPermissions();
    if (perm.receive === "prompt" || perm.receive === "prompt-with-rationale") {
      perm = await PushNotifications.requestPermissions();
    }
    if (perm.receive !== "granted") {
      console.warn("[push] permission denied");
      initialized = false;
      return;
    }

    // Listeners must be registered before register()
    PushNotifications.addListener("registration", async (token) => {
      try {
        const appInfo = await CapApp.getInfo();
        await api.post("/admin/mobile/push/register", {
          token: token.value,
          platform: "android",
          app_version: appInfo.version,
          build_number: appInfo.build,
        });
        console.log("[push] token registered");
      } catch (e) {
        console.error("[push] register failed", e);
      }
    });

    PushNotifications.addListener("registrationError", (err) => {
      console.error("[push] registration error", err);
    });

    PushNotifications.addListener("pushNotificationReceived", async (notification) => {
      // Foreground: FCM does NOT show system tray while app is open, so we manually
      // schedule a local notification so the user still sees it in the tray.
      console.log("[push] received", notification);
      try {
        await LocalNotifications.schedule({
          notifications: [
            {
              id: Date.now() % 2147483647,
              title: notification.title || "AI-Секретарь",
              body: notification.body || "",
              extra: notification.data || {},
              smallIcon: "ic_stat_icon_config_sample",
              channelId: "default",
            },
          ],
        });
      } catch (e) {
        console.error("[push] local notify failed", e);
      }
    });

    PushNotifications.addListener("pushNotificationActionPerformed", (action) => {
      // User tapped a notification — route if deep-link provided
      const link = action.notification.data?.link as string | undefined;
      if (link && typeof link === "string") {
        window.location.hash = link.startsWith("#") ? link : `#${link}`;
      }
    });

    await PushNotifications.register();
  } catch (e) {
    console.error("[push] init failed", e);
    initialized = false;
  }
}

/**
 * Unregister on logout — deletes token on backend so we don't push to stale users.
 */
export async function unregisterPush(): Promise<void> {
  if (!Capacitor.isNativePlatform()) return;
  try {
    // Best-effort: tell backend to drop this device's tokens
    await api.post("/admin/mobile/push/unregister", {}).catch(() => {});
    await PushNotifications.removeAllListeners();
  } catch (e) {
    console.error("[push] unregister failed", e);
  }
  initialized = false;
}
