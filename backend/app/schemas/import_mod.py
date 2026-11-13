from pydantic import BaseModel, ConfigDict, Field


class ImportReportItemErrorDTO(BaseModel):
    """Детализация отклоненной строки при импорте."""
    model_config = ConfigDict(from_attributes=True, populate_by_name=True)

    row_index: int = Field(..., description="Порядковый номер строки в файле")
    raw_title: str | None = Field(default=None, description="Исходный заголовок из строки")
    reason: str = Field(..., description="Причина отклонения на понятном русском языке")


class ImportReportDTO(BaseModel):
    """Сводный отчет по результатам пакетного импорта CSV или JSON."""
    model_config = ConfigDict(from_attributes=True, populate_by_name=True)

    total_received: int = Field(default=0, ge=0, description="Всего обработано строк")
    added_count: int = Field(default=0, ge=0, description="Успешно добавлено новых карточек")
    updated_count: int = Field(default=0, ge=0, description="Обновлено существующих карточек")
    deduplicated_merged_count: int = Field(default=0, ge=0, description="Сведено дубликатов из разных источников")
    flagged_for_moderation_count: int = Field(default=0, ge=0, description="Отправлено в очередь модерации")
    rejected_count: int = Field(default=0, ge=0, description="Отклонено из-за критических ошибок")
    errors: list[ImportReportItemErrorDTO] = Field(
        default_factory=list,
        description="Список всех отклоненных строк с описанием причин",
    )
