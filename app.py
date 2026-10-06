                                "WhatsApp message failed"
                            )

                    else:

                        contact.error_message = None

                    db.session.commit()

        return jsonify({
            "success": True
        }), 200

    except Exception as error:

        print(
            "Webhook error:",
            error
        )

        db.session.rollback()

        return jsonify({

            "success": False,

            "error":
                str(error)

        }), 500


# ============================================================
# HEALTH
# ============================================================

@app.route("/health")
def health():

    database_status = "error"

    try:

        db.session.execute(
            db.text("SELECT 1")
        )

        database_status = "connected"

    except Exception as error:

        return jsonify({

            "status":
                "error",

            "database":
                database_status,

            "whatsapp":
                (
                    "configured"
                    if whatsapp_is_configured()
                    else "not configured"
                ),

            "error":
                str(error)

        }), 500

    return jsonify({

        "status":
            "ok",

        "database":
            database_status,

        "whatsapp":
            (
                "configured"
                if whatsapp_is_configured()
                else "not configured"
            )

    })


# ============================================================
# RUN
# ============================================================

if __name__ == "__main__":

    port = int(
        os.getenv(
            "PORT",
            "5000"
        )
    )

    app.run(

        host="0.0.0.0",

        port=port,

        debug=False
    )
