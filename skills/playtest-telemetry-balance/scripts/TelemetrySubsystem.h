// Plantilla generica: escribe eventos de juego a CSV en <Proyecto>/Saved/Telemetry/.
// Copiar a Source/<Modulo>/, reemplazar MYGAME_API por la macro del modulo (Core y Engine ya estan en un proyecto C++).
// Compilar con el editor CERRADO (UCLASS nuevo). Verificado: compila y escribe el CSV en UE 5.8.4 (TableFlyer, 9-nov-2026).
// Desde C++:  GetGameInstance()->GetSubsystem<UTelemetrySubsystem>()->LogEvent(TEXT("death"), TEXT("p1"), TEXT("storm"), 1.f);
// Desde Blueprint: nodo "Log Event" del subsistema (Get Game Instance Subsystem).
// Mismo formato que telemetry_logger.py: ts,session,build,round,player_id,event,subject,value
#pragma once

#include "CoreMinimal.h"
#include "Subsystems/GameInstanceSubsystem.h"
#include "TelemetrySubsystem.generated.h"

UCLASS()
class MYGAME_API UTelemetrySubsystem : public UGameInstanceSubsystem
{
	GENERATED_BODY()

public:
	virtual void Initialize(FSubsystemCollectionBase& Collection) override;
	virtual void Deinitialize() override;

	UFUNCTION(BlueprintCallable, Category = "Telemetry")
	void LogEvent(const FString& Event, const FString& PlayerId, const FString& Subject, float Value = 0.f);

	UFUNCTION(BlueprintCallable, Category = "Telemetry")
	void SetRound(int32 NewRound) { Round = NewRound; }

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Telemetry")
	FString BuildId = TEXT("dev");

private:
	FString FilePath;
	FString SessionId;
	double StartTime = 0.0;
	int32 Round = 0;

	// Escapa comas, comillas y saltos de linea segun CSV.
	static FString Csv(const FString& In);
};
