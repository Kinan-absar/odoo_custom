# Attendance device change request – 18.0.1.20.133

- First attendance device is automatically trusted if no approved device exists.
- Merely logging in or opening Attendance on any additional device creates no pending record and sends no manager notification.
- An unapproved device displays **Request Device Change**. Only clicking this button creates a pending device record and sends the existing manager mail activities/notifications.
- Repeated requests from an already-pending device do not create duplicate records/alerts.
- Rejected/revoked devices may make an explicit new request.
- Existing trusted device remains active throughout pending and rejected requests. It is revoked only when the Attendance Manager approves the replacement.
- Online and offline attendance remain blocked on devices without trusted status; other portal features are unaffected.
- No changes to existing geofence or offline queue/sync logic.
