import java.io.File

// Console d'administration FootProba : simple fenêtre (WebView) sur /admin du serveur.
// Aucune dépendance : uniquement le système Android.
plugins {
    id("com.android.application")
}

// Adresse du serveur et numéro de construction fournis par la CI :
// ./gradlew assembleRelease -Pfp.server=https://… -Pfp.build=12
val server = (findProperty("fp.server") as String?)?.trim()?.trimEnd('/')
    ?.takeIf { it.isNotEmpty() } ?: "https://footproba.duckdns.org"
val build = (findProperty("fp.build") as String?)?.toIntOrNull() ?: 1

android {
    namespace = "com.footproba.console"
    compileSdk = 36

    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }

    defaultConfig {
        // Identifiant distinct de l'application des joueurs : les deux s'installent côte à côte.
        applicationId = "com.footproba.console"
        minSdk = 26
        targetSdk = 36
        versionCode = build
        versionName = "1.0.$build"
        manifestPlaceholders["serverUrl"] = server
    }

    // Même clé que l'application (secrets de la CI), sinon clé de développement du dépôt.
    signingConfigs {
        create("release") {
            val prodFile = System.getenv("FP_KEYSTORE_FILE")
            if (prodFile != null && File(prodFile).exists()) {
                storeFile = File(prodFile)
                storePassword = System.getenv("FP_KEYSTORE_PASSWORD")
                keyAlias = System.getenv("FP_KEY_ALIAS")
                keyPassword = System.getenv("FP_KEY_PASSWORD")
            } else {
                storeFile = rootProject.file("../app/android/keystore/footprono-dev.jks")
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
