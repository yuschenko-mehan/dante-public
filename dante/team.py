"""Team work implementation: splitting, assigning, running in parallel, retrying, and finishing.
Реалізація командної роботи: розділення, призначення, паралельний запуск, повторні спроби та завершення."""

from dataclasses import dataclass, field
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import List, Dict, Tuple, Set, Callable, Any


@dataclass(frozen=True)
class Part:
    """A part of the task with its ID, description, and involved files.
    Частина завдання з її ідентифікатором, описом та залученими файлами."""
    id: str
    task: str
    files: Tuple[str, ...] = ()


@dataclass
class PartResult:
    """The result of executing a task part.
    Результат виконання частини завдання."""
    part_id: str
    ok: bool
    files: List[str] = field(default_factory=list)
    model: str = ''
    error: str = ''


@dataclass
class TeamResult:
    """The final result of the team's work.
    Кінцевий результат роботи команди."""
    success: bool
    files: List[str] = field(default_factory=list)
    failed_parts: List[str] = field(default_factory=list)


def assign(parts: List[Part], providers: List[Dict[str, Any]], group_size: int = 3, allow_paid: bool = False) -> Dict[str, List[str]]:
    """Assign models to parts.
    Призначити моделі частинам."""
    if not providers:
        raise ValueError("No models available / Немає доступних моделей")
    
    # Filter providers based on allow_paid / Фільтрувати провайдерів на основі дозволу платних
    free_models = [p["name"] for p in providers if not p.get("paid", False)]
    paid_models = [p["name"] for p in providers if p.get("paid", False)]
    
    if not free_models and not allow_paid:
        raise ValueError("No free models available and paid not allowed / Немає безкоштовних моделей, а платні не дозволені")
        
    # Order models: free ones first, then paid ones (if allowed)
    # Порядок моделей: спочатку безкоштовні, потім платні (якщо дозволено)
    all_models = list(free_models)
    if allow_paid:
        all_models.extend(paid_models)
        
    if not all_models:
        raise ValueError("No models available / Немає доступних моделей")
        
    num_free = len(free_models) if free_models else len(all_models)
    if num_free == 0:
        num_free = len(all_models)
        
    assignments = {}
    for i, part in enumerate(parts):
        # Group i starts at model i modulo number of free models so different parts start with different models
        # Група i починається з моделі i за модулем кількості безкоштовних моделей, щоб різні частини починалися з різних моделей
        start_idx = i % num_free
        group = []
        
        # Collect distinct models up to group_size
        # Збирати унікальні моделі до розміру групи
        curr_idx = start_idx
        attempts = 0
        while len(group) < group_size and attempts < len(all_models):
            model = all_models[curr_idx]
            if model not in group:
                group.append(model)
            curr_idx = (curr_idx + 1) % len(all_models)
            attempts += 1
            
        # If paid is allowed, ensure paid models are ALWAYS LAST in the group if included
        # Якщо платні дозволені, переконатися, що платні моделі ЗАВЖДИ ОСТАННІ в групі, якщо вони включені
        if allow_paid:
            free_in_group = [m for m in group if m in free_models]
            paid_in_group = [m for m in group if m in paid_models]
            group = free_in_group + paid_in_group
            
        assignments[part.id] = group
        
    return assignments


def split_conflicts(parts: List[Part]) -> List[Part]:
    """Split and merge parts touching common files.
    Розділити та об'єднати частини, що торкаються спільних файлів."""
    # Union-Find or simple graph component approach
    # Підхід з об'єднанням або компонентами графа
    parent = {}
    
    def find(i):
        if parent[i] == i:
            return i
        parent[i] = find(parent[i])
        return parent[i]

    def union(i, j):
        root_i = find(i)
        root_j = find(j)
        if root_i != root_j:
            parent[root_j] = root_i

    for part in parts:
        parent[part.id] = part.id

    # Map file -> list of part IDs touching it
    # Зпарувати файл -> список ID частин, які його торкаються
    file_to_parts = {}
    for part in parts:
        for f in part.files:
            file_to_parts.setdefault(f, []).append(part.id)

    for f, p_ids in file_to_parts.items():
        first = p_ids[0]
        for p_id in p_ids[1:]:
            union(first, p_id)

    # Group parts by root parent
    # Групувати частини за кореневим батьком
    groups = {}
    part_map = {p.id: p for p in parts}
    
    for part in parts:
        root = find(part.id)
        groups.setdefault(root, []).append(part)

    merged_parts = []
    for root, group_parts in groups.items():
        merged_id = group_parts[0].id
        tasks = [p.task for p in group_parts]
        combined_task = "\n".join(tasks)
        
        files_set = set()
        for p in group_parts:
            files_set.update(p.files)
            
        merged_parts.append(Part(id=merged_id, task=combined_task, files=tuple(sorted(files_set))))
        
    return merged_parts


def run_parts(parts: List[Part], assignment: Dict[str, List[str]], worker: Callable[[Part, List[str]], PartResult], max_parallel: int = 3) -> List[PartResult]:
    """Run parts in parallel with a thread pool.
    Запустити частини паралельно за допомогою пулу потоків."""
    results = []
    
    def run_single(part):
        group = assignment.get(part.id, [])
        try:
            return worker(part, group)
        except Exception as e:
            return PartResult(part_id=part.id, ok=False, error=str(e))

    with ThreadPoolExecutor(max_workers=max_parallel) as executor:
        future_to_part = {executor.submit(run_single, part): part for part in parts}
        for future in as_completed(future_to_part):
            results.append(future.result())
            
    return results


def finish(results: List[PartResult], run_all_tests: Callable[[], bool], retry_part: Callable[[str], PartResult]) -> TeamResult:
    """Finish team work: retry failed parts once through the Academy, then run all tests.
    Завершити командну роботу: повторити невдалі частини один раз через Академію, потім запустити всі тести."""
    final_results = []
    failed_part_ids = []
    
    for res in results:
        if res.ok:
            final_results.append(res)
        else:
            # Retry ONCE through retry_part (the Academy)
            # Повторити ОДИН РАЗ через retry_part (Академія)
            try:
                retry_res = retry_part(res.part_id)
                if retry_res and retry_res.ok:
                    final_results.append(retry_res)
                else:
                    failed_part_ids.append(res.part_id)
                    if retry_res:
                        final_results.append(retry_res)
            except Exception as e:
                failed_part_ids.append(res.part_id)
                final_results.append(PartResult(part_id=res.part_id, ok=False, error=str(e)))
                
    if failed_part_ids:
        return TeamResult(success=False, files=[], failed_parts=sorted(list(set(failed_part_ids))))
        
    # If any part still fails -> TeamResult(False, [], failed part ids) and run_all_tests is NOT called
    # Якщо якась частина все ще не працює -> TeamResult(False, [], failed part ids), і run_all_tests НЕ викликається
    # (Already handled by checking failed_part_ids above)
    
    # Otherwise call run_all_tests() once and return success with the sorted united file list
    # Інакше викликати run_all_tests() один раз і повернути успіх із відсортованим об'єднаним списком файлів
    tests_ok = False
    try:
        tests_ok = run_all_tests()
    except Exception:
        tests_ok = False
        
    if not tests_ok:
        return TeamResult(success=False, files=[], failed_parts=[])
        
    all_files = set()
    for res in final_results:
        for f in res.files:
            all_files.add(f)
            
    return TeamResult(success=True, files=sorted(list(all_files)), failed_parts=[])
