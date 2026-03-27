package com.shaerware.aisecretary;

import android.os.Bundle;
import androidx.core.view.WindowCompat;
import com.getcapacitor.BridgeActivity;

public class MainActivity extends BridgeActivity {
    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        // Enable edge-to-edge: WebView draws behind navigation bar,
        // making env(safe-area-inset-bottom) report the correct value
        WindowCompat.setDecorFitsSystemWindows(getWindow(), false);
    }
}
