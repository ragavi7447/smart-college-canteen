// Firebase Web SDK initialization for Smart College Canteen
import { initializeApp } from "https://www.gstatic.com/firebasejs/10.13.0/firebase-app.js";
import { getAnalytics } from "https://www.gstatic.com/firebasejs/10.13.0/firebase-analytics.js";

export const firebaseConfig = {
  apiKey: "AIzaSyDLsbztc6-6ttrkJnoJWth0JcvyLoDu5aE",
  authDomain: "project-canteen-975f5.firebaseapp.com",
  projectId: "project-canteen-975f5",
  storageBucket: "project-canteen-975f5.firebasestorage.app",
  messagingSenderId: "1056079664291",
  appId: "1:1056079664291:web:194f5b9a59eecbdfc41b16",
  measurementId: "G-LHGDJYLWH0"
};

// Initialize Firebase
export const app = initializeApp(firebaseConfig);
let analytics = null;
try {
  analytics = getAnalytics(app);
} catch (e) {
  // Analytics is only active on http/https protocol
}

window.firebaseApp = app;
window.firebaseAnalytics = analytics;
console.log("🔥 Firebase App Initialized: project-canteen-975f5");
