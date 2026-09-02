package br.com.indaialpapel.sigma;

import android.app.DownloadManager;
import android.content.Context;
import android.net.Uri;
import android.os.Bundle;
import android.os.Environment;
import android.webkit.CookieManager;
import android.webkit.URLUtil;
import android.widget.Toast;

import com.getcapacitor.BridgeActivity;

import java.text.SimpleDateFormat;
import java.util.Date;
import java.util.Locale;

public class MainActivity extends BridgeActivity {
    private static final String SIGMA_HOST = "app.suaempresa.com.br";

    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);

        getBridge().getWebView().setDownloadListener(
                (url, userAgent, contentDisposition, mimeType, contentLength) -> {
                    try {
                        Uri uri = Uri.parse(url);
                        if (!"https".equalsIgnoreCase(uri.getScheme())
                                || !SIGMA_HOST.equalsIgnoreCase(uri.getHost())) {
                            throw new IllegalArgumentException("Download fora do SIGMA");
                        }

                        String fileName = uniqueFileName(
                                URLUtil.guessFileName(url, contentDisposition, mimeType)
                        );
                        DownloadManager.Request request = new DownloadManager.Request(uri);
                        String cookies = CookieManager.getInstance().getCookie(url);

                        if (cookies != null && !cookies.isEmpty()) {
                            request.addRequestHeader("Cookie", cookies);
                        }
                        if (userAgent != null && !userAgent.isEmpty()) {
                            request.addRequestHeader("User-Agent", userAgent);
                        }

                        request.setMimeType(mimeType);
                        request.setTitle(fileName);
                        request.setDescription("Arquivo gerado pelo SIGMA");
                        request.setNotificationVisibility(
                                DownloadManager.Request.VISIBILITY_VISIBLE_NOTIFY_COMPLETED
                        );
                        request.setDestinationInExternalPublicDir(
                                Environment.DIRECTORY_DOWNLOADS,
                                fileName
                        );

                        DownloadManager manager =
                                (DownloadManager) getSystemService(Context.DOWNLOAD_SERVICE);
                        if (manager == null) {
                            throw new IllegalStateException("Gerenciador de downloads indisponivel");
                        }

                        manager.enqueue(request);
                        Toast.makeText(
                                this,
                                "Download iniciado: " + fileName,
                                Toast.LENGTH_LONG
                        ).show();
                    } catch (Exception exception) {
                        Toast.makeText(
                                this,
                                "Nao foi possivel baixar o arquivo.",
                                Toast.LENGTH_LONG
                        ).show();
                    }
                }
        );
    }

    private String uniqueFileName(String originalName) {
        String timestamp = new SimpleDateFormat(
                "yyyyMMdd-HHmmss",
                Locale.ROOT
        ).format(new Date());
        int extensionIndex = originalName.lastIndexOf('.');

        if (extensionIndex > 0 && extensionIndex < originalName.length() - 1) {
            return originalName.substring(0, extensionIndex)
                    + "-" + timestamp
                    + originalName.substring(extensionIndex);
        }
        return originalName + "-" + timestamp;
    }
}
