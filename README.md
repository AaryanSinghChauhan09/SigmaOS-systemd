    # SigmaOS-systemd

    Service unit manager (start/enable/mask/status)

    Part of the **SigmaOS** sovereign operating-system ecosystem — a multi-repository
    distribution modelled on Linux Mint and Omarchy Linux. See the parent
    [`SigmaOS`](https://github.com/AaryanSinghChauhan09/SigmaOS) repository for the
    full component index.

    ## Upstream inspirations
    - https://github.com/linuxmint/systemd-betsy

    ## Design principles applied
    - **Pure Plan / Thin Execute**
- **Fail-Fast**
- **Deterministic Testing**
- **KISS**
- **Information Hiding**

    ## Usage
    Verbs: `enable, disable, start, status, cat`

    ```
    $ sigma-unit --store ./store enable sshd.service
$ sigma-unit --store ./store start sshd.service
$ sigma-unit --store ./store status sshd.service
$ sigma-unit --store ./store cat sshd.service

    ```

    ## Build & test
    ```
    make build
    make test
    ```

    ## Licence
    GNU General Public License v3.0 (FOSS).
