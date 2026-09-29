import java.io.FileInputStream
import java.util.Properties

plugins {
    id("com.android.application")
    id("kotlin-android")
    // The Flutter Gradle Plugin must be applied after the Android and Kotlin Gradle plugins.
    id("dev.flutter.flutter-gradle-plugin")
}

val keystoreProperties = Properties()
val keystorePropertiesFile = rootProject.file("key.properties").takeIf { it.exists() }
    ?: rootProject.file("../key.properties").takeIf { it.exists() }
    ?: file("key.properties").takeIf { it.exists() }

if (keystorePropertiesFile != null && keystorePropertiesFile.exists()) {
    keystoreProperties.load(FileInputStream(keystorePropertiesFile))
}

android {
    namespace = "com.sajjadamin.tinypos"
    compileSdk = 36
    ndkVersion = flutter.ndkVersion

    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }

    kotlinOptions {
        jvmTarget = JavaVersion.VERSION_17.toString()
    }

    defaultConfig {
        applicationId = "com.sajjadamin.tinypos"
        minSdk = flutter.minSdkVersion
        targetSdk = 36
        versionCode = flutter.versionCode
        versionName = flutter.versionName
    }

    signingConfigs {
        create("release") {
            if (keystorePropertiesFile != null && keystorePropertiesFile.exists()) {
                val keyAliasVal = keystoreProperties.getProperty("keyAlias")?.trim()?.removeSurrounding("\"")?.removeSurrounding("'")
                val keyPasswordVal = keystoreProperties.getProperty("keyPassword")?.trim()?.removeSurrounding("\"")?.removeSurrounding("'")
                val storePasswordVal = keystoreProperties.getProperty("storePassword")?.trim()?.removeSurrounding("\"")?.removeSurrounding("'")
                val storeFileVal = keystoreProperties.getProperty("storeFile")?.trim()?.removeSurrounding("\"")?.removeSurrounding("'")

                if (!keyAliasVal.isNullOrBlank()) keyAlias = keyAliasVal
                if (!keyPasswordVal.isNullOrBlank()) keyPassword = keyPasswordVal
                if (!storePasswordVal.isNullOrBlank()) storePassword = storePasswordVal
                if (!storeFileVal.isNullOrBlank()) {
                    val resolvedFile = file(storeFileVal).takeIf { it.exists() }
                        ?: rootProject.file(storeFileVal).takeIf { it.exists() }
                        ?: rootProject.file("../$storeFileVal").takeIf { it.exists() }
                        ?: rootProject.file("app/$storeFileVal").takeIf { it.exists() }
                        ?: file(storeFileVal)
                    storeFile = resolvedFile
                }
            }
        }
    }

    buildTypes {
        release {
            if (keystorePropertiesFile != null && keystorePropertiesFile.exists()) {
                signingConfig = signingConfigs.getByName("release")
            } else {
                signingConfig = signingConfigs.getByName("debug")
            }
        }
    }
}

flutter {
    source = "../.."
}

