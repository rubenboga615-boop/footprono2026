import java.io.File

plugins {
    id("com.android.application")
    // The Flutter Gradle Plugin must be applied after the Android and Kotlin Gradle plugins.
    id("dev.flutter.flutter-gradle-plugin")
}

android {
    namespace = "com.footprono.footprono"
    compileSdk = flutter.compileSdkVersion
    ndkVersion = flutter.ndkVersion

    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }

    defaultConfig {
        applicationId = "com.footprono.footprono"
        // You can update the following values to match your application needs.
        // For more information, see: https://flutter.dev/to/review-gradle-config.
        minSdk = flutter.minSdkVersion
        targetSdk = flutter.targetSdkVersion
        // Uses the version code from pubspec.yaml. When using split APKs, 1000 * ABI_VERSION
        // is added automatically by Flutter. (https://developer.android.com/studio/build/configure-apk-splits#configure-APK-versions)
        // You can force using the value of versionCode by specifying the `-P force-version-code-ignoring-abi=true`
        // flag during build.
        versionCode = flutter.versionCode
        versionName = flutter.versionName
    }

    // Clé de production si FP_KEYSTORE_FILE est défini (secret de la CI),
    // sinon clé de développement du dépôt (android/keystore/footprono-dev.jks).
    signingConfigs {
        create("release") {
            val prodFile = System.getenv("FP_KEYSTORE_FILE")
            if (prodFile != null && File(prodFile).exists()) {
                storeFile = File(prodFile)
                storePassword = System.getenv("FP_KEYSTORE_PASSWORD")
                keyAlias = System.getenv("FP_KEY_ALIAS")
                keyPassword = System.getenv("FP_KEY_PASSWORD")
            } else {
                storeFile = rootProject.file("keystore/footprono-dev.jks")
                storePassword = "footprono-dev"
                keyAlias = "footprono"
                keyPassword = "footprono-dev"
            }
        }
    }

    buildTypes {
        release {
            signingConfig = signingConfigs.getByName("release")
        }
    }
}

kotlin {
    compilerOptions {
        jvmTarget = org.jetbrains.kotlin.gradle.dsl.JvmTarget.JVM_17
    }
}

flutter {
    source = "../.."
}
