# Plantilla de prueba de Automation (C++) para maniobras

Sin verificar contra UE 5.8 (no compilada). Camino recomendado cuando el runner de Python no tenga bucle de ticks. Genérica: `AMyVehiclePawn` es cualquier pawn con movimiento propio y un avance a paso fijo (`StepMovement(Dt)`) que el proyecto expone.

Idea: la prueba abre el mapa, crea el pawn, encola un comando latente que aplica el stick del guion y avanza el movimiento con `Dt` fijo, y al terminar escribe el CSV con encabezado. Después se analiza con `analyze_flight.py`. Un CSV ausente o vacío es FALLA.

```cpp
// Source/<Proyecto>/Tests/FlightManeuverTest.cpp  (sin verificar)
#include "CoreMinimal.h"
#include "Misc/AutomationTest.h"
#include "Tests/AutomationCommon.h"
#include "Misc/FileHelper.h"
#include "Misc/Paths.h"
#include "HAL/PlatformFileManager.h"
#include "GameFramework/Pawn.h"
#include "Editor.h"                       // GEditor: solo con EditorContext
#include "MyVehiclePawn.h"                // ficticio: pawn con SetVirtualStick y StepMovement

IMPLEMENT_SIMPLE_AUTOMATION_TEST(FFlightTurn360Test, "Project.Flight.Turn360",
    EAutomationTestFlags::ProductFilter | EAutomationTestFlags::EditorContext)

DEFINE_LATENT_AUTOMATION_COMMAND_FOUR_PARAMETER(FRunManeuverCommand,
    TWeakObjectPtr<AMyVehiclePawn>, Pawn, double, Elapsed, FString, Csv, double, Duration);

bool FRunManeuverCommand::Update()
{
    if (!Pawn.IsValid()) return true;
    const double Dt = 1.0 / 60.0;                         // paso fijo propio, no depende de los fps
    // aquí: leer el stick del guion en Elapsed (cargado del JSON) y aplicarlo
    Pawn->SetVirtualStick(1.0f, 0.25f, 0.7f, 0.0f);       // ejemplo fijo
    Pawn->StepMovement(Dt);                                // SIN esto el pawn no avanza
    const FVector L = Pawn->GetActorLocation();
    const FRotator R = Pawn->GetActorRotation();
    const FVector V = Pawn->GetVelocity();
    Csv += FString::Printf(TEXT("%f,%f,%f,%f,%f,%f,%f,%f,%f,%f\n"), Elapsed, L.X, L.Y, L.Z,
        R.Pitch, R.Roll, R.Yaw, V.X, V.Y, V.Z);
    Elapsed += Dt;
    if (Elapsed < Duration) return false;
    const FString Path = FPaths::ProjectSavedDir() / TEXT("FlightTests/turn360.csv");
    FFileHelper::SaveStringToFile(Csv, *Path);
    return true;
}

bool FFlightTurn360Test::RunTest(const FString& Parameters)
{
    ADD_LATENT_AUTOMATION_COMMAND(FEditorLoadMap(TEXT("/Game/Maps/FlightTestRange")));  // mapa de pruebas del proyecto
    ADD_LATENT_AUTOMATION_COMMAND(FWaitLatentCommand(1.0f));
    UWorld* World = GEditor ? GEditor->GetEditorWorldContext().World() : nullptr;
    AMyVehiclePawn* Pawn = World ? World->SpawnActor<AMyVehiclePawn>(FVector(0, 0, 30000), FRotator::ZeroRotator) : nullptr;
    if (!TestNotNull(TEXT("pawn creado"), Pawn)) return false;
    FString Csv = TEXT("t,x,y,z,pitch,roll,yaw,vx,vy,vz\n");   // encabezado: sin él el análisis daría NaN
    ADD_LATENT_AUTOMATION_COMMAND(FRunManeuverCommand(Pawn, 0.0, Csv, 25.0));
    return true;
}
```

Notas:

- Si en el editor `FEditorLoadMap` no existe en tu versión, usar `AutomationOpenMap(TEXT("/Game/..."))` (de `Tests/AutomationCommon.h`) y esperar a que cargue antes de crear el pawn (crear el pawn dentro de otro comando latente es más seguro que en `RunTest`).
- Correr con el wrapper: `run-tests.ps1 ... -Filter "Project.Flight"`. `-NullRHI` basta.
- Borrar `Saved/FlightTests/*.csv` antes de correr y revisar que el CSV exista después: `analyze_flight.py` falla si falta o está vacío.
- Con física de Chaos asíncrona el resultado puede variar. Correr 3 veces y comparar con tolerancia de 5 %.
