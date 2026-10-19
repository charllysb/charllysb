import java.util.Properties

plugins {
    id("com.android.application")
    id("org.jetbrains.kotlin.android")
}

// Release signing comes from keystore.properties (local, git-ignored) or from
// environment variables (CI). Without either, only debug builds can be made.
val keystoreProps = Properties().apply {
    rootProject.file("keystore.properties").takeIf { it.exists() }?.inputStream()?.use(::load)
}
fun signingValue(prop: String, env: String): String? = keystoreProps.getProperty(prop) ?: System.getenv(env)

android {
    namespace = "dev.charllys.zapsaver"
    compileSdk = 36

    defaultConfig {
        applicationId = "dev.charllys.zapsaver"
        minSdk = 24
        targetSdk = 36
        versionCode = 2
        versionName = "1.1"
    }

    signingConfigs {
        val storeFilePath = signingValue("storeFile", "ZAPSAVER_KEYSTORE_PATH")
        if (storeFilePath != null) {
            create("release") {
                storeFile = rootProject.file(storeFilePath)
                storePassword = signingValue("storePassword", "ZAPSAVER_KEYSTORE_PASSWORD")
                keyAlias = signingValue("keyAlias", "ZAPSAVER_KEY_ALIAS")
                keyPassword = signingValue("keyPassword", "ZAPSAVER_KEY_PASSWORD")
            }
        }
    }

    buildTypes {
        release {
            isMinifyEnabled = false
            signingConfig = signingConfigs.findByName("release")
        }
    }

    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }

    kotlinOptions {
        jvmTarget = "17"
    }
}

dependencies {
    implementation("androidx.core:core-ktx:1.15.0")
    implementation("androidx.activity:activity-ktx:1.10.1")
    implementation("androidx.lifecycle:lifecycle-runtime-ktx:2.8.7")
    implementation("org.jetbrains.kotlinx:kotlinx-coroutines-android:1.10.1")
    implementation("com.android.billingclient:billing-ktx:8.0.0")
    // Billing pulls in an old Fragment transitively; ActivityResult APIs need 1.3+.
    implementation("androidx.fragment:fragment-ktx:1.8.5")
    // Pure-Java LAME port; Android has no built-in MP3 encoder.
    implementation("de.sciss:jump3r:1.0.5")

    testImplementation("junit:junit:4.13.2")
}
