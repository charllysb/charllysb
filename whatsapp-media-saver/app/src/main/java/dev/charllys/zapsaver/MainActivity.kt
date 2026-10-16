package dev.charllys.zapsaver

import android.os.Bundle
import androidx.activity.ComponentActivity

/** Launcher screen: the app does its work from the share sheet, so this only explains how to use it. */
class MainActivity : ComponentActivity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContentView(R.layout.activity_main)
    }
}
