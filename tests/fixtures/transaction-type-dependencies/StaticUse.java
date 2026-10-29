package fixture;
import org.springframework.stereotype.Service;
@Service class Entry {
    static class Helper { static void work() {} }
    public void run() { Helper.work(); }
}
