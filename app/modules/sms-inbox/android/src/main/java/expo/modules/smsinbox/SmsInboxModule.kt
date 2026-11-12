package expo.modules.smsinbox

import android.Manifest
import android.content.Context
import android.content.pm.PackageManager
import android.net.Uri
import expo.modules.kotlin.exception.Exceptions
import expo.modules.kotlin.modules.Module
import expo.modules.kotlin.modules.ModuleDefinition

class SmsInboxModule : Module() {
  private val context: Context
    get() = appContext.reactContext ?: throw Exceptions.ReactContextLost()

  override fun definition() = ModuleDefinition {
    Name("SmsInbox")

    AsyncFunction("readInbox") { limit: Int, sinceMs: Double ->
      if (context.checkSelfPermission(Manifest.permission.READ_SMS) != PackageManager.PERMISSION_GRANTED) {
        throw IllegalStateException("READ_SMS permission is not granted")
      }
      val messages = mutableListOf<Map<String, Any>>()
      context.contentResolver.query(
        Uri.parse("content://sms/inbox"),
        arrayOf("_id", "address", "date", "body"),
        "date >= ?",
        arrayOf(sinceMs.toLong().toString()),
        "date DESC"
      )?.use { cursor ->
        while (cursor.moveToNext() && messages.size < limit) {
          messages.add(
            mapOf(
              "id" to cursor.getString(0),
              "sender" to (cursor.getString(1) ?: ""),
              "date" to cursor.getLong(2).toDouble(),
              "body" to (cursor.getString(3) ?: "")
            )
          )
        }
      }
      messages
    }
  }
}
