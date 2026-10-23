package fixture;
import org.springframework.stereotype.Service;
@Service class Entry {
    static class Result { static Result obtain() { return null; } }
    static class Failure extends RuntimeException {}
    static class Other extends RuntimeException {}
    public void run(String a, String b, String c, String d, String e, String f) {
        Result value = Result.obtain();
        if (value == null) throw new Failure();
    }
    void unrelated() { throw new Other(); }
}
