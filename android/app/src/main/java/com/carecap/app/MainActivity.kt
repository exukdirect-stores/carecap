package com.carecap.app

import android.annotation.SuppressLint
import android.os.Bundle
import android.view.MenuItem
import android.webkit.WebSettings
import android.webkit.WebView
import android.webkit.WebViewClient
import android.widget.ProgressBar
import androidx.activity.ComponentActivity
import androidx.activity.OnBackPressedCallback

/**
 * CareCap — the care captain's OS.
 *
 * A single-activity WebView shell around the deployed CareCap web app.
 * Everything (dose engine, digests, multi-family auth) runs server-side;
 * the web app's PWA manifest, service worker, and tokens all work as-is
 * because this is a normal browser context with DOM storage enabled.
 */
class MainActivity : ComponentActivity() {

    private lateinit var webView: WebView
    private lateinit var progress: ProgressBar

    @SuppressLint("SetJavaScriptEnabled")
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContentView(R.layout.activity_main)

        progress = findViewById(R.id.progress)
        webView = findViewById(R.id.webview)

        webView.settings.apply {
            javaScriptEnabled = true          // the app is a JS frontend
            domStorageEnabled = true          // localStorage: the captain's token
            cacheMode = WebSettings.LOAD_DEFAULT
        }
        webView.webViewClient = object : WebViewClient() {
            override fun onPageStarted(view: WebView?, url: String?, favicon: android.graphics.Bitmap?) {
                progress.visibility = android.view.View.VISIBLE
            }
            override fun onPageFinished(view: WebView?, url: String?) {
                progress.visibility = android.view.View.GONE
            }
        }

        if (savedInstanceState == null) {
            webView.loadUrl(BuildConfig.BASE_URL)
        }

        // In-app back navigates the web app before closing the app.
        onBackPressedDispatcher.addCallback(this, object : OnBackPressedCallback(true) {
            override fun handleOnBackPressed() {
                if (webView.canGoBack()) webView.goBack() else finish()
            }
        })
    }
}
