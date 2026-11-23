from pathlib import Path
import shutil

from integrations.file_distribution.engine import execute, scan
from integrations.file_distribution.news import NEWS_DIRECTORY
from tests.test_file_distribution_engine import write_minutes


def test_news_preview_and_move_keep_word_and_nested_originals(tmp_path):
    folder = tmp_path / "现场报道"
    photos = folder / "相机原图"
    photos.mkdir(parents=True)
    photo = photos / "DSC_0800.HEIC"
    photo.write_bytes(b"original photo")
    word = write_minutes(folder, name="稿件.docx", text=[
        "医学影像系召开教学研讨会议", "11月19日，医学影像系组织课程研讨，教师围绕案例交流。",
    ])
    single = write_minutes(tmp_path, name="交稿.docx", text=[
        "我院教师赴医院走访", "近日，学院组织教师走访实习基地，与带教教师交流。",
    ])
    minutes = write_minutes(tmp_path)
    attendance = tmp_path / "健康体育部-第7周-考勤表.png"
    attendance.write_bytes(b"attendance")
    archive = tmp_path / NEWS_DIRECTORY
    archive.mkdir()
    write_minutes(archive, name="喜报.docx")
    original_word = word.read_bytes()
    plan = scan(tmp_path, ("news", "minutes", "attendance"))
    by_name = {item.name: item for item in plan.items}
    assert set(by_name) == {folder.name, single.name, minutes.name, attendance.name}
    assert by_name[folder.name].is_directory and not by_name[folder.name].manual_selection
    assert by_name[single.name].kind == "学院新闻"
    assert by_name[minutes.name].kind == "会议纪要"
    assert by_name[attendance.name].kind == "考勤记录"
    assert not scan(tmp_path, "weekly").items[0].is_directory
    assert folder.exists() and single.exists()
    result = execute(plan, [folder.name, single.name])
    assert result.moved == 2
    assert (archive / folder.name / photos.name / photo.name).read_bytes() == b"original photo"
    assert (archive / folder.name / word.name).read_bytes() == original_word
    assert (archive / single.name).is_file()
    assert minutes.exists() and attendance.exists() and not folder.exists() and not single.exists()


def test_weak_candidate_and_mixed_records_have_distinct_controls(tmp_path):
    weak = tmp_path / "编号01"
    weak.mkdir()
    (weak / "稿件.doc").write_bytes(b"legacy Word")
    (weak / "活动照片.jpg").write_bytes(b"photo")
    mixed = tmp_path / "健康体育部活动"
    mixed.mkdir()
    (mixed / "新闻稿.doc").write_bytes(b"legacy Word")
    (mixed / "会议纪要.pdf").write_bytes(b"minutes")
    write_minutes(tmp_path, name="健康体育部开展活动.docx", text=["考勤表", "参会人员：测试"])
    plan = scan(tmp_path, "news")
    rows = {item.name: item for item in plan.items}
    assert set(rows) == {weak.name, mixed.name}
    assert rows[weak.name].status == "ready" and rows[weak.name].manual_selection
    assert rows[mixed.name].status == "review"
    assert execute(plan, [weak.name]).moved == 1


def test_news_folder_changes_and_archive_conflicts_preserve_sources(tmp_path):
    folder = tmp_path / "学院新闻稿"
    folder.mkdir()
    (folder / "新闻稿.doc").write_bytes(b"legacy Word")
    photo = folder / "原图.jpg"
    photo.write_bytes(b"original")
    plan = scan(tmp_path, "news")
    photo.write_bytes(b"modified")
    assert execute(plan, [folder.name]).items[0].status == "changed"
    assert folder.exists()

    target = Path(scan(tmp_path, "news").items[0].destination)
    target.parent.mkdir()
    target.mkdir()
    assert scan(tmp_path, "news").items[0].status == "collision"
    target.rmdir()
    shutil.copytree(folder, target.with_name("以前保存的同一报道"))
    assert scan(tmp_path, "news").items[0].status == "duplicate"
    assert folder.exists()
