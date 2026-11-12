# Trusted Attendance Device - 18.0.1.20.127

- First verified attendance device is automatically trusted when no trusted device exists for the employee.
- Attendance check-in/out requires the trusted device token on the server, in addition to existing portal authorization and GPS/geofence rules.
- Offline attendance events carry the trusted device token and are rejected during sync if the device is not currently trusted.
- A second/new device is registered as Pending Approval and cannot check in/out.
- Attendance Managers can open Attendance > Trusted Devices and use Approve & Replace Current Device. The previous trusted device is revoked automatically.
- Revoked/pending devices cannot perform online attendance. Offline events created on a formerly trusted device will be rejected at sync after revocation.
- Device secrets are not stored in plaintext on the server; only SHA-256 hashes are stored.
- Service-worker cache version bumped to v47 for clean PWA rollout.

Test sequence:
1. Upgrade Employee Portal Suite.
2. On Employee A phone, open Attendance online. The phone should auto-register as Trusted.
3. Check in/out normally and verify GPS behavior remains unchanged.
4. Disable internet and verify offline attendance still works on this phone.
5. Login as Employee A from a second phone and open Attendance. It should show device approval required and buttons should be blocked.
6. As Attendance Manager, open Employee Portal > Attendance > Trusted Devices, open the pending device, then Approve & Replace Current Device.
7. Refresh Attendance on the second phone; it should become trusted. The old phone should no longer be accepted by the server.
