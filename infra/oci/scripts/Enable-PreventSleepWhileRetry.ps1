# Helpers: keep Windows awake while Retry-StagingTerraformApply.ps1 runs (scripts cannot run during sleep).

function Enable-PreventSystemSleep {
    if (-not ("PreventSleep" -as [type])) {
        Add-Type @"
using System;
using System.Runtime.InteropServices;
public static class PreventSleep {
    [DllImport("kernel32.dll", CharSet = CharSet.Auto, SetLastError = true)]
    public static extern uint SetThreadExecutionState(uint esFlags);
    public const uint ES_CONTINUOUS = 0x80000000;
    public const uint ES_SYSTEM_REQUIRED = 0x00000001;
    public const uint ES_DISPLAY_REQUIRED = 0x00000002;
}
"@
    }
    [PreventSleep]::SetThreadExecutionState(
        [PreventSleep]::ES_CONTINUOUS -bor [PreventSleep]::ES_SYSTEM_REQUIRED -bor [PreventSleep]::ES_DISPLAY_REQUIRED
    ) | Out-Null
}

function Disable-PreventSystemSleep {
    if ("PreventSleep" -as [type]) {
        [PreventSleep]::SetThreadExecutionState([PreventSleep]::ES_CONTINUOUS) | Out-Null
    }
}
