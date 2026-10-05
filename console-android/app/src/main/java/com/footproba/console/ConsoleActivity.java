package com.footproba.console;

import android.app.Activity;
import android.app.DownloadManager;
import android.content.ActivityNotFoundException;
import android.content.Intent;
import android.content.pm.PackageManager;
import android.graphics.Color;
import android.graphics.Insets;
import android.net.Uri;
import android.os.Build;
import android.os.Bundle;
import android.os.Environment;
import android.text.Html;
import android.webkit.URLUtil;
import android.webkit.ValueCallback;
import android.webkit.WebChromeClient;
import android.webkit.WebResourceError;
import android.webkit.WebResourceRequest;
import android.webkit.WebSettings;
import android.webkit.WebView;
import android.webkit.WebViewClient;
import android.widget.FrameLayout;
import android.widget.Toast;
import android.window.OnBackInvokedCallback;
import android.window.OnBackInvokedDispatcher;
import android.view.WindowInsets;

/**
 * Console d'administration FootProba : la page /admin du serveur dans une fenêtre dédiée.
 *
 * <p>Seule l'adresse du serveur s'ouvre ici (les autres liens partent dans le navigateur).
 * Les fichiers de la console (exports, rapports) vont dans le dossier Téléchargements et
 * le bouton « choisir un fichier » (publication d'une version) ouvre le sélecteur Android.
 * La session (jeton) vit dans le sessionStorage de la page : fermer l'application
 * déconnecte, comme fermer l'onglet du navigateur.
 */
public class ConsoleActivity extends Activity {
    private static final int PICK_FILE = 1;

    private WebView web;
    private String server;
    private String host;
    private ValueCallback<Uri[]> pending;
    private Object backCallback;
    private boolean backRegistered;

    @Override
    protected void onCreate(Bundle state) {
        super.onCreate(state);
        server = readServer();
        host = Uri.parse(server).getHost();

        web = new WebView(this);
        web.setBackgroundColor(Color.parseColor("#060509"));
        WebSettings s = web.getSettings();
        s.setJavaScriptEnabled(true);
        s.setDomStorageEnabled(true);
        s.setAllowFileAccess(false);
        s.setAllowContentAccess(false);
        s.setUserAgentString(s.getUserAgentString() + " FootProbaConsole/" + versionName());
        web.setWebViewClient(new Client());
        web.setWebChromeClient(new Chrome());
        web.setDownloadListener(this::download);

        FrameLayout root = new FrameLayout(this);
        root.addView(web);
        // Android 15 et plus : l'affichage va jusqu'aux bords ; on garde la page hors des
        // barres système et du clavier.
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.R) {
            root.setOnApplyWindowInsetsListener((v, insets) -> {
                Insets i = insets.getInsets(WindowInsets.Type.systemBars()
                        | WindowInsets.Type.displayCutout() | WindowInsets.Type.ime());
                v.setPadding(i.left, i.top, i.right, i.bottom);
                return WindowInsets.CONSUMED;
            });
        }
        setContentView(root);

        if (state == null || web.restoreState(state) == null) {
            web.loadUrl(server + "/admin/");
        }
    }

    private String readServer() {
        try {
            Bundle meta = getPackageManager()
                    .getApplicationInfo(getPackageName(), PackageManager.GET_META_DATA).metaData;
            String value = meta == null ? null : meta.getString("footproba.server");
            if (value != null && !value.isEmpty()) return value;
        } catch (PackageManager.NameNotFoundException ignored) {
            // Impossible pour notre propre paquet : valeur par défaut ci-dessous.
        }
        return "https://footproba.duckdns.org";
    }

    private String versionName() {
        try {
            return getPackageManager().getPackageInfo(getPackageName(), 0).versionName;
        } catch (PackageManager.NameNotFoundException e) {
            return "?";
        }
    }

    private boolean isServer(Uri uri) {
        return host != null && host.equalsIgnoreCase(uri.getHost());
    }

    private void openOutside(Uri uri) {
        try {
            startActivity(new Intent(Intent.ACTION_VIEW, uri));
        } catch (ActivityNotFoundException e) {
            Toast.makeText(this, "Aucune application pour ouvrir ce lien", Toast.LENGTH_LONG).show();
        }
    }

    /** Lien signé de la console : le gestionnaire de téléchargements d'Android s'en charge. */
    private void download(String url, String agent, String disposition, String mime, long length) {
        Uri uri = Uri.parse(url);
        if (Build.VERSION.SDK_INT < Build.VERSION_CODES.Q || !isServer(uri)) {
            openOutside(uri);
            return;
        }
        String name = URLUtil.guessFileName(url, disposition, mime);
        DownloadManager.Request request = new DownloadManager.Request(uri)
                .setTitle(name)
                .setMimeType(mime)
                .setNotificationVisibility(
                        DownloadManager.Request.VISIBILITY_VISIBLE_NOTIFY_COMPLETED)
                .setDestinationInExternalPublicDir(Environment.DIRECTORY_DOWNLOADS, name);
        DownloadManager manager = getSystemService(DownloadManager.class);
        manager.enqueue(request);
        Toast.makeText(this, "Téléchargement de " + name + " (dossier Téléchargements)",
                Toast.LENGTH_LONG).show();
    }

    private void offline(String reason) {
        String page = "<!doctype html><meta name=viewport content='width=device-width'>"
                + "<body style='background:#060509;color:#ece9f5;font-family:sans-serif;"
                + "display:flex;flex-direction:column;align-items:center;justify-content:center;"
                + "height:90vh;text-align:center;padding:0 24px'>"
                + "<h2>Serveur injoignable</h2><p style='color:#9d97b0'>"
                + Html.escapeHtml(reason) + "</p><p style='color:#9d97b0'>"
                + Html.escapeHtml(server) + "</p>"
                + "<a href='" + Html.escapeHtml(server) + "/admin/' style='margin-top:16px;"
                + "background:#8b5cf6;color:#fff;padding:12px 28px;border-radius:12px;"
                + "text-decoration:none'>Réessayer</a></body>";
        web.loadDataWithBaseURL(server + "/admin/", page, "text/html", "utf-8", null);
    }

    // Retour : revient à la page précédente de la console avant de quitter.
    private void updateBack() {
        if (Build.VERSION.SDK_INT < Build.VERSION_CODES.TIRAMISU) return;
        OnBackInvokedDispatcher dispatcher = getOnBackInvokedDispatcher();
        if (backCallback == null) backCallback = (OnBackInvokedCallback) () -> web.goBack();
        boolean wanted = web.canGoBack();
        if (wanted && !backRegistered) {
            dispatcher.registerOnBackInvokedCallback(OnBackInvokedDispatcher.PRIORITY_DEFAULT,
                    (OnBackInvokedCallback) backCallback);
        } else if (!wanted && backRegistered) {
            dispatcher.unregisterOnBackInvokedCallback((OnBackInvokedCallback) backCallback);
        }
        backRegistered = wanted;
    }

    @Override
    @SuppressWarnings("deprecation")
    public void onBackPressed() {
        if (web.canGoBack()) web.goBack();
        else super.onBackPressed();
    }

    private class Client extends WebViewClient {
        @Override
        public boolean shouldOverrideUrlLoading(WebView view, WebResourceRequest request) {
            Uri uri = request.getUrl();
            if (isServer(uri)) return false;
            openOutside(uri);
            return true;
        }

        @Override
        public void onReceivedError(WebView view, WebResourceRequest request,
                WebResourceError error) {
            if (request.isForMainFrame()) offline(String.valueOf(error.getDescription()));
        }

        @Override
        public void doUpdateVisitedHistory(WebView view, String url, boolean isReload) {
            updateBack();
        }
    }

    private class Chrome extends WebChromeClient {
        @Override
        public boolean onShowFileChooser(WebView view, ValueCallback<Uri[]> callback,
                FileChooserParams params) {
            if (pending != null) pending.onReceiveValue(null);
            pending = callback;
            Intent pick = new Intent(Intent.ACTION_GET_CONTENT)
                    .addCategory(Intent.CATEGORY_OPENABLE)
                    .setType("*/*");
            try {
                startActivityForResult(Intent.createChooser(pick, "Choisir un fichier"), PICK_FILE);
            } catch (ActivityNotFoundException e) {
                pending = null;
                callback.onReceiveValue(null);
            }
            return true;
        }
    }

    @Override
    @SuppressWarnings("deprecation")
    protected void onActivityResult(int request, int result, Intent data) {
        super.onActivityResult(request, result, data);
        if (request != PICK_FILE || pending == null) return;
        pending.onReceiveValue(WebChromeClient.FileChooserParams.parseResult(result, data));
        pending = null;
    }

    @Override
    protected void onSaveInstanceState(Bundle state) {
        super.onSaveInstanceState(state);
        web.saveState(state);
    }

    @Override
    protected void onResume() {
        super.onResume();
        web.onResume();
    }

    @Override
    protected void onPause() {
        web.onPause();
        super.onPause();
    }

    @Override
    protected void onDestroy() {
        web.destroy();
        super.onDestroy();
    }
}
