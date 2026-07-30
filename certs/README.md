# Extra trust anchors for the image build

Drop `.crt` files (PEM) here and the Docker build will trust them. Leave the directory
empty and nothing changes — this is a hook, not a requirement.

## Why this exists

Some networks inspect TLS: a filtering service or a corporate proxy terminates the
connection, reads it, and re-signs it with a certificate authority of its own. The
machine is configured to trust that authority, which is why a browser and a local
`pip install` are perfectly happy — but a fresh `python:3.12-slim` container has never
heard of it, so `pip` inside the build fails with:

```
[SSL: CERTIFICATE_VERIFY_FAILED] certificate verify failed: unable to get local issuer certificate
```

That is not a broken Dockerfile. It is the container correctly refusing a certificate it
cannot trace to anyone it trusts.

## What to put here

Export the root certificate your network signs with, in PEM form, into this directory.
On Windows, where such an authority is installed in the certificate store:

```powershell
$dir = "certs"
Get-ChildItem Cert:\LocalMachine\Root |
  Where-Object { $_.Subject -like "*O=YourAuthorityName*" } |
  Sort-Object Thumbprint -Unique |
  ForEach-Object {
      $b64 = [Convert]::ToBase64String($_.RawData, 'InsertLineBreaks')
      Set-Content -Encoding ascii -Path "$dir\ca-$($_.Thumbprint).crt" `
          -Value "-----BEGIN CERTIFICATE-----`r`n$b64`r`n-----END CERTIFICATE-----"
  }
```

The `.crt` files themselves are **git-ignored**. They describe one machine's network, not
this project, and which authority a person's traffic passes through is not something to
publish in a repository. Anyone building on an ordinary connection needs nothing here.
