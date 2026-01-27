#!/usr/bin/env python3
"""
CLI Админка для AI Secretary System

Использование:
    ./admin.py status              # Статус системы
    ./admin.py tts presets         # Список пресетов TTS
    ./admin.py tts preset warm     # Установить пресет
    ./admin.py tts test "Привет"   # Тестовый синтез
    ./admin.py llm prompt          # Показать промпт
    ./admin.py llm model           # Текущая модель
"""

import sys
import time

import click
import requests
from rich import box
from rich.console import Console
from rich.panel import Panel
from rich.table import Table


console = Console()

# URL оркестратора
ORCHESTRATOR_URL = "http://localhost:8002"


def api_get(endpoint: str):
    """GET запрос к API"""
    try:
        resp = requests.get(f"{ORCHESTRATOR_URL}{endpoint}", timeout=10)
        resp.raise_for_status()
        return resp.json()
    except requests.exceptions.ConnectionError:
        console.print("[red]Ошибка: Оркестратор недоступен[/red]")
        console.print(f"[dim]Проверьте, запущен ли: curl {ORCHESTRATOR_URL}/health[/dim]")
        sys.exit(1)
    except Exception as e:
        console.print(f"[red]Ошибка API: {e}[/red]")
        sys.exit(1)


def api_post(endpoint: str, data: dict):
    """POST запрос к API"""
    try:
        resp = requests.post(f"{ORCHESTRATOR_URL}{endpoint}", json=data, timeout=60)
        resp.raise_for_status()
        return resp.json()
    except requests.exceptions.ConnectionError:
        console.print("[red]Ошибка: Оркестратор недоступен[/red]")
        sys.exit(1)
    except requests.exceptions.HTTPError as e:
        try:
            detail = e.response.json().get("detail", str(e))
        except Exception:
            detail = str(e)
        console.print(f"[red]Ошибка: {detail}[/red]")
        sys.exit(1)
    except Exception as e:
        console.print(f"[red]Ошибка API: {e}[/red]")
        sys.exit(1)


def api_delete(endpoint: str):
    """DELETE запрос к API"""
    try:
        resp = requests.delete(f"{ORCHESTRATOR_URL}{endpoint}", timeout=10)
        resp.raise_for_status()
        return resp.json()
    except requests.exceptions.ConnectionError:
        console.print("[red]Ошибка: Оркестратор недоступен[/red]")
        sys.exit(1)
    except Exception as e:
        console.print(f"[red]Ошибка API: {e}[/red]")
        sys.exit(1)


@click.group()
def cli():
    """AI Secretary Admin CLI"""
    pass


# ============== STATUS ==============


@cli.command()
@click.option("--watch", "-w", is_flag=True, help="Мониторинг в реальном времени")
def status(watch):
    """Показать статус системы"""

    def show_status():
        data = api_get("/admin/status")

        # Заголовок
        console.print()
        console.print(
            Panel.fit("[bold cyan]AI Secretary System[/bold cyan]", subtitle="Status Dashboard")
        )

        # Таблица сервисов
        table = Table(title="Сервисы", box=box.ROUNDED)
        table.add_column("Сервис", style="cyan")
        table.add_column("Статус", justify="center")

        services = data.get("services", {})
        status_icons = {True: "[green]✓ Running[/green]", False: "[red]✗ Stopped[/red]"}

        table.add_row("Voice Clone (XTTS v2)", status_icons[services.get("voice_clone", False)])
        table.add_row("LLM (Gemini)", status_icons[services.get("llm", False)])
        table.add_row("STT (Whisper)", status_icons[services.get("stt", False)])
        table.add_row("Streaming TTS", status_icons[services.get("streaming_tts", False)])

        console.print(table)

        # GPU информация
        gpu_info = data.get("gpu", [])
        if gpu_info:
            gpu_table = Table(title="GPU", box=box.ROUNDED)
            gpu_table.add_column("ID", style="dim")
            gpu_table.add_column("Название", style="cyan")
            gpu_table.add_column("Память", justify="right")

            for gpu in gpu_info:
                mem_str = f"{gpu['used_gb']:.1f} / {gpu['total_gb']:.1f} GB"
                gpu_table.add_row(str(gpu["id"]), gpu["name"], mem_str)

            console.print(gpu_table)

        # TTS конфигурация
        tts_config = data.get("tts_config")
        if tts_config:
            tts_table = Table(title="TTS Configuration", box=box.ROUNDED)
            tts_table.add_column("Параметр", style="cyan")
            tts_table.add_column("Значение")

            tts_table.add_row("Device", tts_config.get("device", "N/A"))
            tts_table.add_row(
                "Default Preset", f"[yellow]{tts_config.get('default_preset', 'N/A')}[/yellow]"
            )
            tts_table.add_row("Voice Samples", str(tts_config.get("samples_count", 0)))

            console.print(tts_table)

        # LLM конфигурация
        llm_config = data.get("llm_config")
        if llm_config:
            llm_table = Table(title="LLM Configuration", box=box.ROUNDED)
            llm_table.add_column("Параметр", style="cyan")
            llm_table.add_column("Значение")

            llm_table.add_row("Model", f"[yellow]{llm_config.get('model_name', 'N/A')}[/yellow]")
            llm_table.add_row("History Length", str(llm_config.get("history_length", 0)))

            prompt = llm_config.get("system_prompt", "")
            if len(prompt) > 50:
                prompt = prompt[:50] + "..."
            llm_table.add_row("System Prompt", f"[dim]{prompt}[/dim]")

            console.print(llm_table)

        # Streaming TTS статистика
        streaming_stats = data.get("streaming_tts_stats")
        if streaming_stats:
            console.print(
                f"\n[dim]Streaming TTS Cache: {streaming_stats.get('cache_size', 0)} items[/dim]"
            )

    if watch:
        console.print("[dim]Нажмите Ctrl+C для выхода[/dim]")
        try:
            while True:
                console.clear()
                show_status()
                time.sleep(2)
        except KeyboardInterrupt:
            console.print("\n[dim]Выход[/dim]")
    else:
        show_status()


# ============== TTS ==============


@cli.group()
def tts():
    """Управление TTS (голосовым синтезом)"""
    pass


@tts.command("presets")
def tts_presets():
    """Список доступных пресетов TTS"""
    data = api_get("/admin/tts/presets")

    table = Table(title="TTS Presets", box=box.ROUNDED)
    table.add_column("Пресет", style="cyan")
    table.add_column("Название")
    table.add_column("Temp", justify="right")
    table.add_column("Speed", justify="right")
    table.add_column("", justify="center")

    current = data.get("current", "")

    for name, preset in data.get("presets", {}).items():
        marker = "[green]◀ current[/green]" if name == current else ""
        table.add_row(
            name,
            preset.get("display_name", ""),
            str(preset.get("temperature", "")),
            str(preset.get("speed", "")),
            marker,
        )

    console.print(table)


@tts.command("preset")
@click.argument("name")
def tts_set_preset(name):
    """Установить пресет TTS"""
    data = api_post("/admin/tts/preset", {"preset": name})

    console.print(
        f"[green]✓[/green] Пресет изменён на: [yellow]{data['preset']}[/yellow] ({data.get('display_name', '')})"
    )
    settings = data.get("settings", {})
    console.print(
        f"  temperature: {settings.get('temperature', 'N/A')}, speed: {settings.get('speed', 'N/A')}"
    )


@tts.command("test")
@click.argument("text")
@click.option("--preset", "-p", default="natural", help="Пресет для синтеза")
def tts_test(text, preset):
    """Тестовый синтез речи"""
    console.print(f"[dim]Синтезирую: '{text}'...[/dim]")

    with console.status("[bold green]Синтез...[/bold green]"):
        data = api_post("/admin/tts/test", {"text": text, "preset": preset})

    console.print("[green]✓[/green] Готово!")
    console.print(f"  Файл: [cyan]{data.get('file', 'N/A')}[/cyan]")
    console.print(f"  Длительность: {data.get('duration_sec', 0):.2f} сек")
    console.print(f"  Время синтеза: {data.get('synthesis_time_sec', 0):.2f} сек")
    console.print(f"  RTF: {data.get('rtf', 0):.2f}x")


@tts.command("cache")
@click.option("--clear", is_flag=True, help="Очистить кэш")
def tts_cache(clear):
    """Статистика/очистка кэша streaming TTS"""
    if clear:
        data = api_delete("/admin/tts/cache")
        console.print(f"[green]✓[/green] Кэш очищен: {data.get('cleared_items', 0)} элементов")
    else:
        data = api_get("/admin/tts/cache")
        console.print(f"Cache size: [cyan]{data.get('cache_size', 0)}[/cyan] items")
        console.print(f"Active sessions: [cyan]{data.get('active_sessions', 0)}[/cyan]")


# ============== LLM ==============


@cli.group()
def llm():
    """Управление LLM (языковой моделью)"""
    pass


@llm.command("prompt")
@click.argument("new_prompt", required=False)
def llm_prompt(new_prompt):
    """Показать/изменить системный промпт"""
    if new_prompt:
        data = api_post("/admin/llm/prompt", {"prompt": new_prompt})
        console.print("[green]✓[/green] Промпт обновлён")
        console.print(f"[dim]{data.get('prompt', '')}[/dim]")
    else:
        data = api_get("/admin/llm/prompt")
        console.print(
            Panel(
                data.get("prompt", "N/A"),
                title="System Prompt",
                subtitle=f"Model: {data.get('model', 'N/A')}",
            )
        )


@llm.command("model")
@click.argument("new_model", required=False)
def llm_model(new_model):
    """Показать/изменить модель LLM"""
    if new_model:
        data = api_post("/admin/llm/model", {"model": new_model})
        console.print(
            f"[green]✓[/green] Модель изменена на: [yellow]{data.get('model', '')}[/yellow]"
        )
    else:
        data = api_get("/admin/llm/model")
        console.print(f"Текущая модель: [yellow]{data.get('model', 'N/A')}[/yellow]")
        console.print("[dim]Доступные: gemini-2.5-flash, gemini-2.5-pro, gemini-2.0-flash[/dim]")


@llm.command("history")
@click.option("--clear", is_flag=True, help="Очистить историю")
def llm_history(clear):
    """Показать/очистить историю диалога"""
    if clear:
        data = api_delete("/admin/llm/history")
        console.print(
            f"[green]✓[/green] История очищена: {data.get('cleared_messages', 0)} сообщений"
        )
    else:
        data = api_get("/admin/llm/history")
        count = data.get("count", 0)

        if count == 0:
            console.print("[dim]История диалога пуста[/dim]")
        else:
            console.print(f"[cyan]История диалога ({count} сообщений):[/cyan]\n")
            for msg in data.get("history", []):
                role = msg.get("role", "")
                content = msg.get("content", "")
                if role == "user":
                    console.print(
                        f"[blue]User:[/blue] {content[:100]}{'...' if len(content) > 100 else ''}"
                    )
                else:
                    console.print(
                        f"[green]Assistant:[/green] {content[:100]}{'...' if len(content) > 100 else ''}"
                    )


@llm.command("test")
@click.argument("question")
def llm_test(question):
    """Тестовый запрос к LLM"""
    console.print(f"[dim]Запрос: '{question}'[/dim]")

    with console.status("[bold green]Генерация ответа...[/bold green]"):
        try:
            resp = requests.post(f"{ORCHESTRATOR_URL}/chat", json={"text": question}, timeout=30)
            resp.raise_for_status()
            data = resp.json()
        except Exception as e:
            console.print(f"[red]Ошибка: {e}[/red]")
            return

    console.print(Panel(data.get("response", "N/A"), title="Ответ Лидии", border_style="green"))


# ============== MAIN ==============

if __name__ == "__main__":
    cli()
