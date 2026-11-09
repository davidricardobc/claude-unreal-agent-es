// Ver el header. Verificado en UE 5.8.4 (FFileHelper append, FPaths, FGuid).
#include "TelemetrySubsystem.h"
#include "HAL/FileManager.h"
#include "HAL/PlatformTime.h"
#include "Misc/DateTime.h"
#include "Misc/FileHelper.h"
#include "Misc/Guid.h"
#include "Misc/Paths.h"
#include "HAL/PlatformFileManager.h"

FString UTelemetrySubsystem::Csv(const FString& In)
{
	if (In.Contains(TEXT(",")) || In.Contains(TEXT("\"")) || In.Contains(TEXT("\n")))
	{
		return TEXT("\"") + In.Replace(TEXT("\""), TEXT("\"\"")) + TEXT("\"");
	}
	return In;
}

void UTelemetrySubsystem::Initialize(FSubsystemCollectionBase& Collection)
{
	Super::Initialize(Collection);
	StartTime = FPlatformTime::Seconds();
	SessionId = FDateTime::Now().ToString(TEXT("%Y%m%d_%H%M%S")) + TEXT("_") + FGuid::NewGuid().ToString().Left(4);
	const FString Dir = FPaths::ProjectSavedDir() / TEXT("Telemetry");
	FPlatformFileManager::Get().GetPlatformFile().CreateDirectoryTree(*Dir);
	FilePath = Dir / FString::Printf(TEXT("telemetry_%s.csv"), *SessionId);
	FFileHelper::SaveStringToFile(TEXT("ts,session,build,round,player_id,event,subject,value\n"), *FilePath,
		FFileHelper::EEncodingOptions::ForceUTF8WithoutBOM);
}

void UTelemetrySubsystem::Deinitialize()
{
	LogEvent(TEXT("session_end"), TEXT(""), TEXT(""), 0.f);
	Super::Deinitialize();
}

void UTelemetrySubsystem::LogEvent(const FString& Event, const FString& PlayerId, const FString& Subject, float Value)
{
	const double Ts = FPlatformTime::Seconds() - StartTime;
	const FString Line = FString::Printf(TEXT("%.3f,%s,%s,%d,%s,%s,%s,%g\n"), Ts, *SessionId, *Csv(BuildId), Round,
		*Csv(PlayerId), *Csv(Event), *Csv(Subject), Value);
	// Abre y cierra el archivo por evento: sirve para eventos espaciados (muertes, rondas), no para cada frame.
	// Con eventos por tick (dano continuo), acumular en un TArray y vaciarlo cada ~1 s.
	// En PIE con servidor y cliente, cada GameInstance escribe su propio archivo: registrar solo en autoridad.
	FFileHelper::SaveStringToFile(Line, *FilePath, FFileHelper::EEncodingOptions::ForceUTF8WithoutBOM,
		&IFileManager::Get(), FILEWRITE_Append);
}
